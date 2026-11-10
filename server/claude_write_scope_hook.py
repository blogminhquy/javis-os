"""PreToolUse hook that keeps Claude Code's own Write/Edit inside the brain on a run below Full access (2026-11-10).

A loop, reminder or Kanban job at the "auto" level runs Claude Code with a tool whitelist: Read, Write, Edit, Glob,
Grep, LS plus the hub. The whitelist checks tool NAMES. Write and Edit are Claude Code's own tools, they take any path
on the machine, and the hub's rule for files that run or configure code (`mcp_hub._ghi_vung_bao_ve`, 2026-11-05) only
covers the hub's `javis_write_file`. So text an auto job read (a web page, an email, a customer message) could make it
write `<brain>/Javis/loops/x.md` with `mode: full`, or `<brain>/plugins/x/plugin.py`, and climb to Full access or to
Python inside the server.

On a whitelisted run that is not at Full access this hook refuses a write that
  - lands outside the brain and outside the folder the run works in, or
  - lands on a path that runs or configures code there (`team_gate.protected_rel`).
The owner's chat and every Full-access run are untouched (no whitelist, or level `full`). A gated Team step keeps its own
hook. Like claude_secret_hook.py this wraps `ClaudeSDK._options` from outside: claude_sdk_engine.py is pinned byte for
byte to the source the native trial path was qualified with.
"""
from __future__ import annotations

import os
from pathlib import Path

_MARK = "_javis_write_scope_hook"
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_PATH_KEYS = ("file_path", "notebook_path", "path")


def restricted(engine) -> bool:
    """Does this engine run a whitelisted background job below Full access?"""
    if not getattr(engine, "allowed_tools", None):
        return False
    if getattr(engine, "team_gate", None):
        return False
    mode = str(getattr(engine, "javis_mode", None) or "").strip().lower()
    if not mode:
        return True          # a whitelist with no level attached: the safe background lane, never Full access
    if mode == "gated":
        return False
    try:
        import mcp_catalog
        return mcp_catalog.effective_perm("full", mode) != "full"
    except Exception:  # noqa: BLE001
        return mode != "full"


def roots_of(engine) -> list:
    out = []
    for raw in (getattr(engine, "javis_vault", None), getattr(engine, "cwd", None)):
        if not raw:
            continue
        try:
            p = Path(str(raw)).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if p not in out:
            out.append(p)
    return out


def refusal_for(tool_name: str, tool_input, roots: list, cwd=None) -> str:
    """Why this call is refused, or "" when it may run. Pure: no engine, no SDK."""
    if tool_name not in _WRITE_TOOLS:
        return ""
    inp = tool_input if isinstance(tool_input, dict) else {}
    raw = next((str(inp[k]) for k in _PATH_KEYS if inp.get(k)), "")
    if not raw:
        return ""            # nothing to judge: Claude Code itself rejects a write with no path
    try:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path(str(cwd or (roots[0] if roots else os.getcwd()))) / p
        p = p.resolve()
    except (OSError, ValueError):
        return _text(raw, "không đọc được đường dẫn")
    import team_gate
    for root in roots:
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if team_gate.protected_rel(rel):
            return _text(raw, "đây là nơi chứa mã chạy hoặc việc chạy toàn quyền (plugins/, Javis/, .claude, .git, "
                              "cấu hình engine)")
        return ""
    return _text(raw, "nằm ngoài bộ não và thư mục làm việc của việc này")


def _text(path: str, why: str) -> str:
    return (f"Javis CHẶN ghi vào '{path}': {why}. Việc này đang chạy dưới mức Toàn quyền nên chỉ ghi được file thường "
            "trong bộ não đang làm việc. Đây là rào bảo mật, không phải lỗi ổ đĩa hay sandbox. Ghi nội dung vào chỗ "
            "khác trong bộ não (ví dụ drafts/), hoặc đưa nội dung vào câu trả lời để chủ tự lưu.")


def make_hook(engine):
    roots = roots_of(engine)
    cwd = getattr(engine, "cwd", None)
    tag = str(getattr(engine, "tag", "") or "")

    async def write_scope_hook(input_data, tool_use_id, context):
        """PreToolUse. Fails closed for the write tools: an error inside the check refuses the write."""
        name = str((input_data or {}).get("tool_name") or "")
        if name not in _WRITE_TOOLS:
            return {}
        try:
            why = refusal_for(name, (input_data or {}).get("tool_input") or {}, roots, cwd)
        except Exception as e:  # noqa: BLE001
            why = f"Javis không kiểm được đường dẫn ghi của lời gọi này ({type(e).__name__}), đã chặn."
        if not why:
            return {}
        try:
            import security_log
            security_log.record("agent_secret_blocked", detail=f"claude:{name} write scope; {tag[:40]}")
        except Exception:  # noqa: BLE001
            pass
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": why}}

    setattr(write_scope_hook, _MARK, True)
    return write_scope_hook


def add_to_options(engine, opts):
    """Add the hook to built ClaudeAgentOptions when `engine` is a restricted run. Returns `opts`."""
    if opts is None or not hasattr(opts, "hooks") or not restricted(engine):
        return opts
    from claude_agent_sdk import HookMatcher
    hooks = dict(getattr(opts, "hooks", None) or {})
    pre = list(hooks.get("PreToolUse") or [])
    if any(getattr(h, _MARK, False) for m in pre for h in (getattr(m, "hooks", None) or [])):
        return opts
    hooks["PreToolUse"] = [HookMatcher(matcher=None, hooks=[make_hook(engine)])] + pre
    opts.hooks = hooks
    return opts


def install() -> bool:
    """Wrap ClaudeSDK._options once. Idempotent. False when the installed SDK has no PreToolUse hooks."""
    import claude_sdk_engine as eng
    cls = eng.ClaudeSDK
    f = cls._options
    while f is not None:                     # whichever order the wrappers of _options went on
        if getattr(f, _MARK, False):
            return True
        f = getattr(f, "__wrapped__", None)
    if not cls.pre_tool_hooks_supported():
        return False
    original = cls._options

    def _options(self):
        opts = original(self)
        if getattr(self, "trial_profile", None) is not None:
            return opts
        return add_to_options(self, opts)

    setattr(_options, _MARK, True)
    _options.__wrapped__ = original
    cls._options = _options
    return True
