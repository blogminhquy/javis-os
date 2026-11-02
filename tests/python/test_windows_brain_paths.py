"""Javis finds agy and grok where the official Windows installers really put them.

    python tests/run.py windows_brain_paths

Found by the desktop installer smoke test (0.439.0) on a clean windows-latest runner: the
Antigravity installer writes %LOCALAPPDATA%\\agy\\bin\\agy.exe and the Grok installer writes
%USERPROFILE%\\.grok\\bin\\grok.exe, and each only adds its folder to the USER PATH in the
registry. A Javis started right after the install (the setup wizard's "Open now", or an
already-running Explorer) still has the old PATH, and its finders did not look in either
folder, so the Models page said "not installed" for two brains that were installed.

The test lays out exactly those two files in a temp home, empties PATH, and asks the server's
own finders.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


tmp = Path(tempfile.mkdtemp())
home = tmp / "home"
local = home / "AppData" / "Local"
agy = local / "agy" / "bin" / "agy.exe"
grok = home / ".grok" / "bin" / "grok.exe"
for f in (agy, grok):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"MZ")

os.environ.update({"USERPROFILE": str(home), "HOME": str(home), "LOCALAPPDATA": str(local),
                   "PATH": str(tmp / "empty"), "JAVIS_STATE_DIR": str(tmp / "state")})
for k in ("JAVIS_AGY_BIN", "JAVIS_GROK_BIN", "APPDATA"):
    os.environ.pop(k, None)
(tmp / "state").mkdir()

import claude_cli  # noqa: E402
from antigravity_cli import find_antigravity_cli  # noqa: E402
from grok_cli import find_grok_cli  # noqa: E402

check("finds agy.exe in %LOCALAPPDATA%\\agy\\bin with that folder off PATH",
      find_antigravity_cli() == str(agy), find_antigravity_cli())
check("finds grok.exe in %USERPROFILE%\\.grok\\bin with that folder off PATH",
      find_grok_cli() == str(grok), find_grok_cli())
check("both folders are in the shared Windows search list (every finder uses it)",
      r"%LOCALAPPDATA%\agy\bin" in claude_cli._THU_MUC_BIN_WINDOWS
      and r"%USERPROFILE%\.grok\bin" in claude_cli._THU_MUC_BIN_WINDOWS)
inst = (ROOT / "install.ps1").read_text(encoding="utf-8")
check("install.ps1 summary looks in the same two folders",
      '"agy\\bin"' in inst and '".grok\\bin"' in inst)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All windows_brain_paths tests passed.")
