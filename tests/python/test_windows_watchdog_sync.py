"""The Windows watchdog follows the autostart switch, so machines installed before it get it too (PR #1868 follow-up).

    python tests/run.py windows_watchdog_sync      (no Windows needed: the task and the script calls are faked)

Checks: autostart on and no task registers it; a task already there or a hand-made opt-out is left alone; autostart off
removes it without opting out; off Windows nothing runs; the script knows `remove` and the opt-out marker; the server
wires the switch and a start-up catch-up a minute after start.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wd-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import windows_watchdog as ww  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


RUNS, STATE = [], {"installed": False}
ww._run = lambda action: (RUNS.append(action), STATE.update(installed=(action == "install")))[0] is None
ww.installed = lambda: STATE["installed"]
real_os_name = ww.os.name


class _Os:
    name = "nt"

    def __getattr__(self, k):
        return getattr(os, k)


ww.os = _Os()
check("autostart on, no task: registered", ww.sync(True) == "installed" and RUNS == ["install"], RUNS)
RUNS.clear()
check("task already there: left alone", ww.sync(True) == "kept" and RUNS == [])
check("autostart off: removed, not opted out", ww.sync(False) == "removed" and RUNS == ["remove"] and not ww.opted_out())
RUNS.clear()
(Path(os.environ["JAVIS_STATE_DIR"]) / ww.OFF_MARKER).write_text("x")
check("removed by hand: never registered again", ww.opted_out() and ww.sync(True) == "kept" and RUNS == [])
ww.os = os
check("off Windows nothing runs", ww.sync(True) == "skipped" and ww.sync(False) == "skipped" and RUNS == [])

ps1 = (ROOT / "javis-watchdog.ps1").read_text(encoding="utf-8")
check("script: uninstall leaves the opt-out marker, install clears it, remove does neither",
      '$OffMarker = Join-Path $StateDir "watchdog-off"' in ps1 and '"remove" {' in ps1
      and "Set-Content -Path $OffMarker" in ps1 and "Remove-Item $OffMarker" in ps1)
check("script stays plain ASCII", all(b < 128 for b in (ROOT / "javis-watchdog.ps1").read_bytes()))
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("the autostart switch syncs the watchdog", "target=windows_watchdog.sync, args=(enabled,)" in main_src)
check("a start-up catch-up a minute after start, only with autostart on",
      "async def _windows_watchdog_catch_up" in main_src and "await asyncio.sleep(60)" in main_src
      and "windows_watchdog.sync, True" in main_src)
check(".gitignore keeps the marker out of git", "server/watchdog-off" in (ROOT / ".gitignore").read_text(encoding="utf-8"))
check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
