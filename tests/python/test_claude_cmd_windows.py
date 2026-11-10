"""Windows: the Claude Agent SDK must never be handed npm's claude.cmd shim. Run by hand / CI:

    python tests/run.py claude_cmd_windows

Owner report 2026-11-10: after an update every Claude turn died with
"CLIConnectionError: Refusing to execute batch script '...\\npm\\claude.CMD'". The SDK (which now
updates itself inside the 0.2.x series) refuses to spawn a .cmd/.bat as the CLI, and Javis passed
it whatever PATH resolved, which on an `npm install -g` machine is the shim.

Covers: the native claude.exe is found from the shim (shim text, npm package layout, native
installer), the placeholder stub is skipped, a shim-only machine lets the SDK use its bundled
binary, nothing changes off Windows, and both SDK call sites go through the one helper.

Touches no network.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cmdwin-")
os.environ.pop("JAVIS_CLAUDE_CLI", None)
os.environ.pop("JAVIS_CLAUDE_BIN", None)

import claude_cli as cc  # noqa: E402

_fails = []


def check(name, ok):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        _fails.append(name)


def big(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(cc._NATIVE_EXE_MIN_BYTES + 10)
    return path


def shim(folder: Path, body: str = "@ECHO off\r\nnode cli.js %*\r\n", name: str = "claude.CMD") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(body, encoding="utf-8")
    return p


_keep = (cc._is_windows, cc._home_dir, cc.tim_binary, cc._duong_dan_tim_binary, os.environ.get("PATH"))
home = Path(tempfile.mkdtemp(prefix="javis-home-"))
cc._home_dir = lambda: home
cc._duong_dan_tim_binary = lambda: ""
os.environ["PATH"] = ""
try:
    # ---- off Windows nothing changes ----
    cc._is_windows = lambda: False
    s0 = shim(Path(tempfile.mkdtemp()) / "npm")
    big(s0.parent / "claude.exe")
    check("off Windows a .cmd path is returned untouched", cc.native_claude_exe(str(s0)) == str(s0))

    cc._is_windows = lambda: True
    check("is_batch_script: .CMD from PATHEXT, .bat, trailing dot", all(
        cc.is_batch_script(x) for x in (r"C:\a\claude.CMD", "claude.bat", "claude.cmd. ")))
    check("is_batch_script: an .exe is not one", not cc.is_batch_script(r"C:\a\claude.exe"))
    check("a native path passes through", cc.native_claude_exe(r"C:\x\claude.exe") == r"C:\x\claude.exe")
    check("None stays None", cc.native_claude_exe(None) is None)

    # ---- the shim names the executable (npm's current layout) ----
    d1 = Path(tempfile.mkdtemp()) / "npm"
    s1 = shim(d1, '@ECHO off\r\nSETLOCAL\r\n"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"   %*\r\n')
    e1 = big(d1 / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
    check("executable named inside the shim is used", cc.native_claude_exe(str(s1)) == str(e1))

    # ---- old shim (node cli.js) but the platform package sits beside it ----
    d2 = Path(tempfile.mkdtemp()) / "npm"
    s2 = shim(d2, '@ECHO off\r\n"%dp0%\\node.exe" "%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js" %*\r\n')
    big(d2 / "node.exe")
    e2 = big(d2 / "node_modules" / "@anthropic-ai" / "claude-code-win32-x64" / "claude.exe")
    check("node.exe in the shim is never mistaken for the CLI; platform package is found",
          cc.native_claude_exe(str(s2)) == str(e2))

    # ---- placeholder stub is skipped, native installer copy is taken ----
    d3 = Path(tempfile.mkdtemp()) / "npm"
    s3 = shim(d3)
    stub = d3 / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    stub.parent.mkdir(parents=True)
    stub.write_bytes(b"MZ stub")
    check("shim only (stub exe): the shim is returned so direct spawns keep working",
          cc.native_claude_exe(str(s3)) == str(s3))
    e3 = big(home / ".local" / "bin" / "claude.exe")
    check("native installer's ~/.local/bin/claude.exe wins over the shim",
          cc.native_claude_exe(str(s3)) == str(e3))

    # ---- what the SDK receives ----
    cc.tim_binary = lambda ten: str(s3)
    check("SDK gets the native exe, never the shim", cc.claude_cli_for_sdk() == str(e3))
    e3.unlink()
    check("shim-only machine: SDK gets no cli_path and falls back to its bundled claude.exe",
          cc.claude_cli_for_sdk() == "")
    cc.tim_binary = lambda ten: str(s1)
    check("find_claude_cli also prefers the native exe",
          cc.find_claude_cli() == str(e1) and cc.claude_cli_for_sdk() == str(e1))
    os.environ["JAVIS_CLAUDE_CLI"] = str(s1)
    check("JAVIS_CLAUDE_CLI pointing at a shim is upgraded too", cc.claude_cli_for_sdk() == str(e1))
    os.environ["JAVIS_CLAUDE_CLI"] = r"C:\py\claude_agent_sdk\_bundled\claude.exe"
    check("the SDK's own _bundled binary is never passed back", cc.claude_cli_for_sdk() == "")
    os.environ.pop("JAVIS_CLAUDE_CLI")
    cc.tim_binary = lambda ten: None
    check("no CLI at all gives an empty cli_path", cc.claude_cli_for_sdk() == "")

    # ---- the pinned engine reads JAVIS_CLAUDE_CLI first: that is where the fix reaches it ----
    def engine_cli_path():
        """Exactly what the pinned ClaudeSDK._options does with cli_path."""
        cc.use_native_claude_for_sdk()
        c = (os.environ.get("JAVIS_CLAUDE_CLI") or "").strip() or (cc.tim_binary("claude") or "")
        return c if c and "_bundled" not in c.replace("\\", "/") else ""

    _bund = cc._sdk_bundled_claude
    try:
        cc.tim_binary = lambda ten: str(s1)
        check("engine gets the native exe, not the shim", engine_cli_path() == str(e1))
        check("it is Javis's own value in the env", cc._SDK_CLI_ENV["set"] == str(e1))
        cc.tim_binary = lambda ten: str(e1)
        check("PATH resolves a real exe again: Javis removes its own override",
              engine_cli_path() == str(e1) and "JAVIS_CLAUDE_CLI" not in os.environ)
        cc.tim_binary = lambda ten: str(s3)
        fake_bundled = str(big(Path(tempfile.mkdtemp()) / "claude_agent_sdk" / "_bundled" / "claude.exe"))
        cc._sdk_bundled_claude = lambda: fake_bundled
        check("shim only: engine passes no cli_path, so the SDK runs its bundled claude.exe",
              engine_cli_path() == "" and os.environ.get("JAVIS_CLAUDE_CLI") == fake_bundled)
        os.environ.pop("JAVIS_CLAUDE_CLI", None); cc._SDK_CLI_ENV["set"] = ""
        cc._sdk_bundled_claude = lambda: None
        check("shim only and no bundled exe: nothing is invented (the SDK explains how to fix it)",
              engine_cli_path() == str(s3) and "JAVIS_CLAUDE_CLI" not in os.environ)
        os.environ["JAVIS_CLAUDE_CLI"] = r"D:\tools\claude.exe"
        check("a user's own JAVIS_CLAUDE_CLI executable is left alone",
              engine_cli_path() == r"D:\tools\claude.exe" and cc._SDK_CLI_ENV["set"] == "")
        os.environ["JAVIS_CLAUDE_CLI"] = str(s1)
        check("a user's JAVIS_CLAUDE_CLI naming a shim is upgraded", engine_cli_path() == str(e1))
        os.environ.pop("JAVIS_CLAUDE_CLI", None); cc._SDK_CLI_ENV["set"] = ""
        cc._is_windows = lambda: False
        cc.tim_binary = lambda ten: str(s1)
        check("off Windows the env is never touched",
              engine_cli_path() == str(s1) and "JAVIS_CLAUDE_CLI" not in os.environ)
        cc._is_windows = lambda: True
    finally:
        cc._sdk_bundled_claude = _bund
        os.environ.pop("JAVIS_CLAUDE_CLI", None); cc._SDK_CLI_ENV["set"] = ""

    # ---- the real SDK agrees: what we hand over is not a batch script to it ----
    try:
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport as T
        import platform
        _sys = platform.system
        platform.system = lambda: "Windows"
        try:
            cc.tim_binary = lambda ten: str(s1)
            check("SDK refuses the raw shim (the bug) and accepts what Javis now passes",
                  T._is_windows_batch_cli(str(s1)) and not T._is_windows_batch_cli(cc.claude_cli_for_sdk()))
        finally:
            platform.system = _sys
    except ImportError:
        print("  skip SDK cross-check (claude-agent-sdk too old or absent)")
finally:
    cc._is_windows, cc._home_dir, cc.tim_binary, cc._duong_dan_tim_binary = _keep[:4]
    os.environ["PATH"] = _keep[4] or ""

# ---- both SDK call sites use the helper ----
eng = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
voice = (SERVER / "voice_brain.py").read_text(encoding="utf-8")
src = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
check("chat engine (pinned source) reads JAVIS_CLAUDE_CLI before PATH",
      'os.environ.get("JAVIS_CLAUDE_CLI")' in eng and '"_bundled" not in' in eng)
check("the one factory that builds ClaudeSDK applies the fix first",
      "use_native_claude_for_sdk()" in src.split("eng = ClaudeSDK(")[0][-600:])
check("voice brain asks claude_cli_for_sdk", "claude_cli_for_sdk()" in voice)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_claude_cmd_windows: all pass")
