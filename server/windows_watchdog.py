"""The Windows watchdog follows the autostart switch (2026-11-27, PR #1868 follow-up).

`javis-watchdog.ps1` registers a per-user Task Scheduler task that restarts Javis when /health stops answering.
`install.ps1` sets it up on a new machine only, so every machine installed before it never got one. Here the server
keeps it in step with the autostart switch, the one place the owner already said "keep Javis running":

  - autostart on and no task: register it once at start-up (and when the switch is turned on);
  - autostart turned off: remove it, a watchdog would otherwise start Javis the owner meant to keep off;
  - `javis-watchdog.bat uninstall` leaves `watchdog-off` in the state dir, and then nothing here registers it again.

Everything is best effort and never raises: a missing script, an old Windows without the ScheduledTasks module, or a
refused registration only leaves things as they were, and the reason goes to stderr.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import winproc

TASK_NAME = "JavisOS Watchdog"
OFF_MARKER = "watchdog-off"
TIMEOUT_S = 120


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _state_dir() -> Path:
    return Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).resolve().parent)))


def opted_out() -> bool:
    """The owner removed the watchdog by hand (`javis-watchdog.bat uninstall`)."""
    return (_state_dir() / OFF_MARKER).exists()


def installed() -> bool:
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, timeout=30,
                           creationflags=winproc.no_window())
        return r.returncode == 0
    except Exception:  # noqa: BLE001 - unknown counts as missing; install is idempotent (-Force)
        return False


def _run(action: str) -> bool:
    script = _root() / "javis-watchdog.ps1"
    if os.name != "nt" or not script.exists():
        return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), action],
                           capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(_root()),
                           creationflags=winproc.no_window())
    except Exception as e:  # noqa: BLE001 - see the module docstring
        print(f"[watchdog] {action}: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        print(f"[watchdog] {action} failed: {(r.stdout or r.stderr or '').strip()[:300]}", file=sys.stderr)
    return r.returncode == 0


def sync(autostart_on: bool) -> str:
    """Bring the task in line with the autostart switch. Returns what was done: installed, removed, kept, skipped."""
    if os.name != "nt":
        return "skipped"
    if autostart_on:
        if opted_out() or installed():
            return "kept"
        return "installed" if _run("install") else "skipped"
    if installed():
        # `remove`, not `uninstall`: turning autostart off is not the owner opting out of the watchdog for good.
        return "removed" if _run("remove") else "skipped"
    return "kept"
