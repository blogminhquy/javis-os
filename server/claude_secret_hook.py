"""PreToolUse hook that keeps every Claude Code turn away from Javis' secret files (owner incident 2026-11-09).

Lives in its own module on purpose: `claude_sdk_engine.py` is pinned byte for byte to the source the native trial path
was qualified with (docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json), so, like
claude_bg_wait.py and the wrappers in claude_cli.py, this wraps `ClaudeSDK._options` from outside instead of editing it.
`claude_cli` installs it where it builds every Claude engine (chat, loops, reminders, bots, Teams).

The hook asks secret_guard.check_tool on every tool call (Bash, Read, Edit, Write, Grep, Glob...), at every permission
level, and denies a call that touches settings.json in the state folder, .secret_key, sessions, tokens, the security
log or a plan login. Each refusal is written to the security log. A gated Team step keeps its own PreToolUse hook: this
one is added next to it. A qualified trial profile (`trial_profile`) builds its own options and is left untouched.
"""
from __future__ import annotations

_MARK = "_javis_secret_hook"


async def secret_guard_hook(input_data, tool_use_id, context):
    """PreToolUse: deny a call that reads or writes a secret file of Javis. Fails open on an error inside the guard
    itself: it is a tripwire on top of the other rails, never the only one."""
    try:
        import secret_guard
        name = str((input_data or {}).get("tool_name") or "")
        tool_input = (input_data or {}).get("tool_input") or {}
        hit = secret_guard.check_tool(name, tool_input)
    except Exception:  # noqa: BLE001
        return {}
    if not hit:
        return {}
    secret_guard.note_blocked(f"claude:{name}", hit, str(tool_input)[:80])
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": secret_guard.refusal(hit)}}


def add_to_options(opts):
    """Add the hook to built ClaudeAgentOptions, next to any PreToolUse hook already there. Returns `opts`."""
    if opts is None or not hasattr(opts, "hooks"):
        return opts
    from claude_agent_sdk import HookMatcher
    hooks = dict(getattr(opts, "hooks", None) or {})
    pre = list(hooks.get("PreToolUse") or [])
    if any(secret_guard_hook in (getattr(m, "hooks", None) or []) for m in pre):
        return opts
    hooks["PreToolUse"] = [HookMatcher(matcher=None, hooks=[secret_guard_hook])] + pre
    opts.hooks = hooks
    return opts


def install() -> bool:
    """Wrap ClaudeSDK._options once. Idempotent. False when the installed SDK has no PreToolUse hooks."""
    import claude_sdk_engine as eng
    cls = eng.ClaudeSDK
    if getattr(cls._options, _MARK, False):
        return True
    if not cls.pre_tool_hooks_supported():
        return False
    original = cls._options

    def _options(self):
        opts = original(self)
        if getattr(self, "trial_profile", None) is not None:
            return opts
        try:
            return add_to_options(opts)
        except Exception:  # noqa: BLE001 - the guard must never stop a turn from starting
            return opts

    setattr(_options, _MARK, True)
    _options.__wrapped__ = original
    cls._options = _options
    return True
