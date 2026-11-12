"""The reason `claude` printed when it exited, in place of the SDK's "Check stderr output for details".

When the `claude` process ends with a non-zero code before it sends a result, claude-agent-sdk raises
`ProcessError("Command failed with exit code N", stderr="Check stderr output for details")`. That second string is a
fixed placeholder: the SDK hands the real stderr to the caller's callback and keeps none of it. `ClaudeSDK` does
collect those lines (`_stderr_tail`), but only quoted them for a startup timeout, so the chat showed

    SDK engine: ProcessError: Command failed with exit code 1 (exit code: 1)
    Error output: Check stderr output for details

and nothing to act on (customer report, 12/11/2026). Measured on Claude Code 2.1.322 with SDK 0.2.172, four ways to
get exactly that message, each with the cause sitting in `_stderr_tail`:

  - Javis runs as root: "--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons"
  - a bad MCP config: "Error: Invalid MCP configuration:" plus the detail on the next line
  - a flag this `claude` does not know: "error: unknown option '--...'"
  - a bad `--settings` value: "Error: Settings file not found: ..."

Lives in its own module on purpose: `claude_sdk_engine.py` is pinned byte for byte to the source the native trial
path was qualified with, so, like claude_secret_hook.py, this wraps `ClaudeSDK.query` from outside. `claude_cli`
installs it where it builds every Claude engine, so chat, Telegram, loops, reminders and Kanban work all get it.
`claude_warm` runs its own loop and calls `rewrite` itself.
"""
from __future__ import annotations

import re

_MARK = "_javis_exit_reason"
_PLACEHOLDER = "check stderr output for details"
_EXIT_CODE = re.compile(r"exit code:?\s*(-?\d+)", re.I)
_QUOTED_LINES = 3
_LINE_CHARS = 200


def is_bare_exit(text) -> bool:
    """True for the SDK's exit-code error that carries no reason of its own."""
    return _PLACEHOLDER in str(text or "").lower()


def _tail(stderr_lines) -> list:
    out = []
    for line in stderr_lines or ():
        # A quoted line is shown to the user: no long dashes (project rule, they also trip text-to-speech).
        s = str(line).strip().replace("—", "-").replace("–", "-")
        if s:
            out.append(s[:_LINE_CHARS])
    return out[-_QUOTED_LINES:]


def explain(text, stderr_lines=()):
    """The sentence shown instead of the bare exit-code error, or None when `text` is not that error.

    The conclusion comes first: a bot's "last turn FAILED" card shows only the first 160 characters."""
    if not is_bare_exit(text):
        return None
    import localefmt
    m = _EXIT_CODE.search(str(text))
    code = m.group(1) if m else "?"
    tail = _tail(stderr_lines)
    seen = " ".join(tail).lower()
    if "cannot be used with root/sudo" in seen:
        vi = ("Claude Code từ chối chạy vì Javis đang chạy bằng tài khoản root: ở mức Toàn quyền nó không cho bỏ qua "
              "bước hỏi quyền dưới root. Chạy Javis bằng một tài khoản thường; hoặc nếu máy này dành riêng cho Javis "
              "(VPS, container) thì thêm dòng IS_SANDBOX=1 vào file .env của Javis rồi khởi động lại.")
        en = ("Claude Code refused to run because Javis runs as root: at Full access it will not skip permission "
              "prompts under root. Run Javis as a regular user; or, if this machine is dedicated to Javis (a VPS, a "
              "container), add the line IS_SANDBOX=1 to Javis' .env file and restart.")
    elif "invalid mcp configuration" in seen:
        vi = ("Claude Code không khởi động được vì cấu hình nguồn dữ liệu (MCP) gửi cho nó không hợp lệ. Mở trang "
              "Kết nối, xem lại nguồn vừa thêm hoặc vừa sửa rồi gửi lại tin nhắn.")
        en = ("Claude Code could not start because the data source (MCP) configuration it was given is invalid. "
              "Open the Connections page, review the source just added or edited, then send the message again.")
    elif "unknown option" in seen:
        vi = ("Claude Code trên máy không hiểu một tuỳ chọn Javis gửi, thường vì bản đang cài đã cũ. Cập nhật "
              "Claude Code (lệnh `claude update`) rồi gửi lại tin nhắn.")
        en = ("The Claude Code on this machine does not know an option Javis passed, usually because the installed "
              "version is old. Update Claude Code (`claude update`), then send the message again.")
    else:
        vi = f"Claude Code dừng với mã thoát {code} trước khi trả lời."
        en = f"Claude Code stopped with exit code {code} before answering."
    if tail:
        quoted = " | ".join(tail)
        vi += f' Claude Code in ra: "{quoted}"'
        en += f' Claude Code printed: "{quoted}"'
    else:
        vi += (" Nó không in ra lý do nào. Chạy thử lệnh `claude` trong terminal của máy đang chạy Javis để xem "
               "lỗi, hoặc gửi log của server cho người hỗ trợ.")
        en += (" It printed no reason. Run `claude` in a terminal on the machine running Javis to see the error, "
               "or send the server log to support.")
    return localefmt.chu(vi, en)


def rewrite(ev, stderr_lines=()):
    """`ev` with its bare exit-code error replaced by the explained one. Any other event comes back untouched, and so
    does a lost thread (`resume_failed`), which callers handle by priming a new one."""
    try:
        if not isinstance(ev, dict) or ev.get("type") != "error" or ev.get("resume_failed"):
            return ev
        better = explain(ev.get("content"), stderr_lines)
        return {**ev, "content": better} if better else ev
    except Exception:  # noqa: BLE001 - wording an error must never lose the error itself
        return ev


def install() -> bool:
    """Wrap `ClaudeSDK.query` once. Idempotent. A qualified trial profile keeps the SDK's own wording."""
    import claude_sdk_engine as eng
    cls = eng.ClaudeSDK
    if getattr(cls.query, _MARK, False):
        return True
    original = cls.query

    async def query(self, prompt):
        stream = original(self, prompt)
        try:
            async for ev in stream:
                if getattr(self, "trial_profile", None) is None:
                    ev = rewrite(ev, getattr(self, "_stderr_tail", ()))
                yield ev
        finally:
            await stream.aclose()

    setattr(query, _MARK, True)
    query.__wrapped__ = original
    cls.query = query
    return True
