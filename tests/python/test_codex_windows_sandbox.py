"""On Windows, Codex gets `windows.sandbox` so `--sandbox workspace-write` really allows writes (#1133).

    python tests/run.py codex_windows_sandbox

The bug: with no `[windows] sandbox` in config.toml, Codex on Windows quietly downgrades `workspace-write` to
`read-only`. Every background job at `auto` on a native Windows install could not write its output and stopped as if
it waited for the owner. Setting `windows.sandbox="unelevated"` (no admin prompt) makes the session really
`workspace-write`; the reporter checked it with codex-cli 0.162.1.

Pinned here (Windows is simulated, CI runs on Linux):
  1. Windows + a sandbox: both the `codex exec` argv and the `codex app-server` argv carry the override
  2. full access (no sandbox): no override
  3. not Windows: no override, argv as before
  4. a `[windows] sandbox` already in config.toml of that Codex home is kept (no override that would beat it)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-codex-win-"))

import claude_cli  # noqa: E402
import codex_steer  # noqa: E402

fails = []
OVERRIDE = 'windows.sandbox="unelevated"'


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def has_override(argv):
    return any(a == "-c" and b == OVERRIDE for a, b in zip(argv, argv[1:]))


def make_cli(sandbox, home):
    cli = claude_cli.CodexCLI(cwd=tempfile.mkdtemp(prefix="javis-codex-win-cwd-"), tag="bg-test")
    cli.sandbox = sandbox
    cli.codex_home = str(home)
    cli.transport = "ws"
    return cli


empty_home = Path(tempfile.mkdtemp(prefix="javis-codex-win-home-"))
(empty_home / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")

# 1. Windows + sandbox
with patch.object(claude_cli, "_windows", lambda: True):
    cli = make_cli("workspace-write", empty_home)
    exec_argv = cli._build_args()
    app_argv = codex_steer._args(cli, None)
    check("1. codex exec carries windows.sandbox", has_override(exec_argv), exec_argv)
    check("1. the override sits before the exec subcommand",
          has_override(exec_argv[:exec_argv.index("exec")]), exec_argv)
    check("1. --sandbox workspace-write is still passed", "workspace-write" in exec_argv, exec_argv)
    check("1. codex app-server carries windows.sandbox", has_override(app_argv), app_argv)
    check("1. read-only gets it too", has_override(make_cli("read-only", empty_home)._build_args()))

    # 2. full access
    full = make_cli(None, empty_home)
    check("2. full access: no override", not has_override(full._build_args()) and not has_override(codex_steer._args(full, None)))

    # 4. a choice already in config.toml
    chosen = Path(tempfile.mkdtemp(prefix="javis-codex-win-home2-"))
    (chosen / "config.toml").write_text('[windows]\nsandbox = "elevated"\n', encoding="utf-8")
    kept = make_cli("workspace-write", chosen)
    check("4. config.toml choice kept (exec)", not has_override(kept._build_args()), kept._build_args())
    check("4. config.toml choice kept (app-server)", not has_override(codex_steer._args(kept, None)))
    no_cfg = make_cli("workspace-write", Path(tempfile.mkdtemp(prefix="javis-codex-win-home3-")))
    check("4. no config.toml at all: override added", has_override(no_cfg._build_args()))

# 3. not Windows
with patch.object(claude_cli, "_windows", lambda: False):
    cli = make_cli("workspace-write", empty_home)
    check("3. Linux/macOS: no override (exec)", not has_override(cli._build_args()))
    check("3. Linux/macOS: no override (app-server)", not has_override(codex_steer._args(cli, None)))

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
