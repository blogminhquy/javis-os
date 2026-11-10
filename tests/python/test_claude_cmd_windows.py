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
    _raw0 = cc._tim_binary_raw
    cc._tim_binary_raw = lambda ten: str(s1)
    try:
        check("find_claude_cli also prefers the native exe",
              cc.find_claude_cli() == str(e1) and cc.claude_cli_for_sdk() == str(e1))
    finally:
        cc._tim_binary_raw = _raw0
    os.environ["JAVIS_CLAUDE_CLI"] = str(s1)
    check("JAVIS_CLAUDE_CLI pointing at a shim is upgraded too", cc.claude_cli_for_sdk() == str(e1))
    os.environ["JAVIS_CLAUDE_CLI"] = r"C:\py\claude_agent_sdk\_bundled\claude.exe"
    check("the SDK's own _bundled binary is never passed back", cc.claude_cli_for_sdk() == "")
    os.environ.pop("JAVIS_CLAUDE_CLI")
    cc.tim_binary = lambda ten: None
    check("no CLI at all gives an empty cli_path", cc.claude_cli_for_sdk() == "")

    # ---- tim_binary("claude") is what the pinned claude_sdk_engine.py asks; it must be SDK-safe ----
    cc.tim_binary = _keep[2]
    _raw, _bund = cc._tim_binary_raw, cc._sdk_bundled_claude
    try:
        cc._tim_binary_raw = lambda ten: str(s1)
        check("tim_binary('claude') answers the native exe, not the shim", cc.tim_binary("claude") == str(e1))
        check("tim_binary of another name is untouched", cc.tim_binary("codex") == str(s1))
        cc._tim_binary_raw = lambda ten: str(s3)
        fake_bundled = str(big(Path(tempfile.mkdtemp()) / "claude_agent_sdk" / "_bundled" / "claude.exe"))
        cc._sdk_bundled_claude = lambda: fake_bundled
        got = cc.tim_binary("claude")
        check("shim only: tim_binary answers the SDK's bundled exe, which the engine drops so the SDK picks it",
              got == fake_bundled and "_bundled" in got.replace("\\", "/"))
        check("shim only: find_claude_cli still answers the user's own install for direct spawns",
              cc.find_claude_cli() == str(s3))
        cc._sdk_bundled_claude = lambda: None
        check("shim only and no bundled exe: the shim comes back (the SDK then explains how to fix it)",
              cc.tim_binary("claude") == str(s3))
        cc._is_windows = lambda: False
        check("off Windows tim_binary is the plain lookup", cc.tim_binary("claude") == str(s3))
        cc._is_windows = lambda: True
    finally:
        cc._tim_binary_raw, cc._sdk_bundled_claude = _raw, _bund

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
check("chat engine (pinned source) still asks tim_binary('claude'), the function fixed here",
      '_tim("claude")' in eng and '"_bundled" not in' in eng)
check("voice brain asks claude_cli_for_sdk", "claude_cli_for_sdk()" in voice)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_claude_cmd_windows: all pass")
