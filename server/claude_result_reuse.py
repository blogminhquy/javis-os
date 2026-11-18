"""Claude Code's side of tool_result_reuse: drop a turn's record of repeated results when Claude Code compacts (2026-11-17).

The hub hands a Claude Code turn a one-line reference in place of a byte-identical repeat of a Javis tool result
(tool_result_reuse, part 3). That is only right while the earlier copy is still in Claude Code's conversation, and
Claude Code summarises its conversation when it runs long. The SDK announces that with a PreCompact hook; this module
adds one that forgets the current turn's record, so after a compaction every repeat goes out whole again. The hook
changes nothing Claude Code sees and returns no decision, so it cannot block or alter a compaction.

Kept out of claude_sdk_engine.py on purpose: that file must stay byte for byte the qualified native source
(tests/python/test_plan_limits.py, test_claude_cho_viec_nen_0453.py). Like claude_secret_hook, this wraps
ClaudeSDK._options once; claude_cli installs it before the secret hook, which must stay the outermost wrapper.
"""
from __future__ import annotations

_MARK = "_javis_result_reuse_hook"


async def compact_hook(input_data, tool_use_id, context):
    """PreCompact: forget this turn's record of repeated tool results. Never blocks, never decides."""
    try:
        import tool_result_reuse
        tool_result_reuse.forget_current_turn()
    except Exception:  # noqa: BLE001 - a saving never stands in the way of a compaction
        pass
    return {}


def add_to_options(opts):
    """Add the PreCompact hook to built ClaudeAgentOptions, next to any already there. Returns `opts`."""
    if opts is None or not hasattr(opts, "hooks"):
        return opts
    from claude_agent_sdk import HookMatcher
    hooks = dict(getattr(opts, "hooks", None) or {})
    pre = list(hooks.get("PreCompact") or [])
    if any(compact_hook in (getattr(m, "hooks", None) or []) for m in pre):
        return opts
    hooks["PreCompact"] = pre + [HookMatcher(matcher=None, hooks=[compact_hook])]
    opts.hooks = hooks
    return opts


def install() -> bool:
    """Wrap ClaudeSDK._options once. Idempotent. False when the installed SDK has no hooks."""
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
        if getattr(self, "trial_profile", None) is not None:   # a qualification trial runs the exact options
            return opts
        try:
            return add_to_options(opts)
        except Exception:  # noqa: BLE001 - a saving must never stop a turn from starting
            return opts

    setattr(_options, _MARK, True)
    _options.__wrapped__ = original
    cls._options = _options
    return True
