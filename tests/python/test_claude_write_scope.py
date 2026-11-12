"""Claude Code's own Write/Edit stay inside the brain on a run below Full access (security, 2026-11-10).

    python tests/run.py claude_write_scope

An "auto" loop, reminder or Kanban job runs Claude Code with a whitelist of tool NAMES (Read, Write, Edit...). Write and
Edit take any path, and the hub's protected-path rule only covers the hub's own file tool. Text such a job read could
make it write a Full-access loop or a plugin. The hook in claude_write_scope_hook.py closes that.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-wscope-")).resolve()
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
(_TMP / "state").mkdir()
BRAIN = _TMP / "brain"
(BRAIN / "drafts").mkdir(parents=True)
(BRAIN / "plugins").mkdir()
OTHER = _TMP / "other-brain"
OTHER.mkdir()

import claude_write_scope_hook as ws  # noqa: E402
import team_gate  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


class Eng:
    def __init__(self, allowed=None, mode=None, vault=str(BRAIN), cwd=str(BRAIN), gate=""):
        self.allowed_tools, self.javis_mode, self.javis_vault, self.cwd = allowed, mode, vault, cwd
        self.team_gate, self.tag, self.trial_profile = gate, "loop:x", None


SAFE = ["Read", "Write", "Edit", "Glob", "Grep", "LS", "mcp__javis"]

# ---- which runs are restricted ----
check("auto job with a whitelist is restricted", ws.restricted(Eng(SAFE, "auto")))
check("suggest job with a whitelist is restricted", ws.restricted(Eng(SAFE, "suggest")))
check("a whitelist with no level attached is restricted", ws.restricted(Eng(SAFE, None)))
check("the owner's chat (no whitelist) is not", not ws.restricted(Eng(None, "full")))
check("a Full-access job is not", not ws.restricted(Eng(None, "full")) and not ws.restricted(Eng(SAFE, "full")))
check("a gated Team step keeps its own hook", not ws.restricted(Eng(SAFE, "auto", gate="g1")))

# ---- what a restricted run may write ----
roots = ws.roots_of(Eng(SAFE, "auto"))
ok = lambda tool, path: ws.refusal_for(tool, {"file_path": path}, roots, str(BRAIN)) == ""   # noqa: E731
check("an ordinary file in the brain (absolute path)", ok("Write", str(BRAIN / "drafts" / "a.md")))
check("an ordinary file in the brain (relative path)", ok("Edit", "drafts/a.md"))
check("a new folder in the brain", ok("Write", "06 - Sources/moi/x.md"))
for bad in ("plugins/x/plugin.py", "plugins/x/plugin.yaml", "Javis/loops/x.md", "Javis/reminders.json",
            ".claude/settings.json", ".git/config", ".grok/config.toml", "CLAUDE.md", "sub/.git/hooks/pre-commit",
            "Plugins/x/plugin.py", "javis/loops/x.md", "claude.md", ".GIT/config", "plugins./x.py"):
    check(f"refused: {bad}", not ok("Write", bad))
check("refused: a file outside the brain", not ok("Write", str(OTHER / "a.md")))
check("refused: the state directory", not ok("Write", str(_TMP / "state" / "plugins" / "x" / "plugin.py")))
check("refused: climbing out with ..", not ok("Write", "drafts/../../other-brain/a.md"))
check("refused: /etc", not ok("Edit", "/etc/cron.d/x"))
check("NotebookEdit is judged by notebook_path",
      ws.refusal_for("NotebookEdit", {"notebook_path": "/etc/x.ipynb"}, roots, str(BRAIN)) != "")
try:
    os.symlink(str(OTHER), str(BRAIN / "lien-ket"))
    check("refused: a symlink in the brain that leads outside", not ok("Write", "lien-ket/a.md"))
except OSError:
    pass
check("read tools are never judged here", ws.refusal_for("Read", {"file_path": "/etc/passwd"}, roots) == "")
check("the refusal says it is a permission rule, not a disk error",
      "rào bảo mật" in ws.refusal_for("Write", {"file_path": "/etc/x"}, roots))

# a job that works in a repo folder next to the brain may write there, and only there
REPO = _TMP / "repo"
REPO.mkdir()
r2 = ws.roots_of(Eng(SAFE, "auto", cwd=str(REPO)))
check("the folder the run works in is in scope too",
      ws.refusal_for("Write", {"file_path": "src/a.py"}, r2, str(REPO)) == ""
      and ws.refusal_for("Write", {"file_path": str(BRAIN / "drafts/b.md")}, r2, str(REPO)) == "")

# ---- team_gate.protected_rel ignores case ----
check("protected_rel: exact spellings as before", team_gate.protected_rel("plugins/a.py")
      and team_gate.protected_rel("Javis/loops/a.md") and team_gate.protected_rel("x/CLAUDE.md")
      and not team_gate.protected_rel("drafts/a.md") and not team_gate.protected_rel("notes/plugins.md"))
check("protected_rel: other spellings of the same folders", team_gate.protected_rel("Plugins/a.py")
      and team_gate.protected_rel("JAVIS/loops/a.md") and team_gate.protected_rel("x/claude.md")
      and team_gate.protected_rel(".Claude/settings.json"))

# ---- the hook itself, and its place on the engine ----
hook = ws.make_hook(Eng(SAFE, "auto"))
deny = asyncio.run(hook({"tool_name": "Write", "tool_input": {"file_path": "plugins/x/plugin.py"}}, "t", None))
check("hook denies a protected write", deny.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", deny)
check("hook lets an ordinary write through",
      asyncio.run(hook({"tool_name": "Write", "tool_input": {"file_path": "drafts/a.md"}}, "t", None)) == {})
check("hook ignores other tools",
      asyncio.run(hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "t", None)) == {})

import claude_sdk_engine  # noqa: E402
import claude_secret_hook  # noqa: E402
if claude_sdk_engine.ClaudeSDK.pre_tool_hooks_supported():
    check("install wraps ClaudeSDK._options", ws.install())
    claude_secret_hook.install()
    check("the secret hook stays the outermost wrapper",
          getattr(claude_sdk_engine.ClaudeSDK._options, "_javis_secret_hook", False))
    top = claude_sdk_engine.ClaudeSDK._options
    ws.install(); claude_secret_hook.install()
    check("installing again does not stack wrappers", claude_sdk_engine.ClaudeSDK._options is top)

    def pre_hooks(**kw):
        e = claude_sdk_engine.ClaudeSDK(system_prompt="x", cwd=str(BRAIN), tag="loop:t", allowed_tools=kw.get("allowed"))
        e.javis_mode, e.javis_vault = kw.get("mode"), str(BRAIN)
        pre = (getattr(e._options(), "hooks", None) or {}).get("PreToolUse") or []
        return [h for m in pre for h in (m.hooks or [])]
    check("an auto job carries the write-scope hook",
          any(getattr(h, "_javis_write_scope_hook", False) for h in pre_hooks(allowed=SAFE, mode="auto")))
    check("and still the secret hook", claude_secret_hook.secret_guard_hook in pre_hooks(allowed=SAFE, mode="auto"))
    check("the owner's chat does not",
          not any(getattr(h, "_javis_write_scope_hook", False) for h in pre_hooks(allowed=None, mode="full")))
else:
    print("skip  SDK without PreToolUse hooks")
check("claude_cli installs it where it builds every Claude engine, before the secret hook",
      (lambda t: 0 < t.find("claude_write_scope_hook.install()") < t.find("claude_secret_hook.install()"))(
          (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8")))

if _fails:
    print(f"\nFAIL - {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_claude_write_scope")
