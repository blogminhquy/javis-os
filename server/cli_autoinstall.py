"""State of the CLIs the Docker container installs by itself at boot (0.85.1).

`docker/entrypoint.sh` installs Antigravity CLI (`agy`) and Grok Build (`grok`) in the background
when they are missing, and writes one line per CLI into `<JAVIS_HOME_PERSIST>/.cli-auto-install/<bin>`:
`installing <epoch>`, `ok <epoch>` or `failed <epoch>`. This module only READS those files, so the
Models page can say "Javis is installing it" instead of handing a Hostinger user a command they have
no terminal to type into.

Outside Docker the folder does not exist and every answer is "" (nothing to say), which leaves the
native install path (install.sh / install.ps1) exactly as it was.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# An install that never wrote its result (container killed mid-download) must not show "installing"
# forever: after this long the card falls back to the manual command.
STUCK_AFTER_S = 15 * 60


def state_dir() -> Path:
    return Path(os.getenv("JAVIS_HOME_PERSIST") or "/data/home") / ".cli-auto-install"


def state(binary: str) -> str:
    """"installing", "failed", "ok", or "" when the container never tried (not Docker, or disabled)."""
    try:
        raw = (state_dir() / binary).read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return ""
    if not raw:
        return ""
    word = raw[0]
    try:
        at = float(raw[1]) if len(raw) > 1 else 0.0
    except ValueError:
        at = 0.0
    if word == "installing":
        return "failed" if at and time.time() - at > STUCK_AFTER_S else "installing"
    return word if word in ("ok", "failed") else ""


def log_path() -> str:
    """Where the installers' output went, for the owner (or support) to read when one failed."""
    return str(state_dir() / "install.log")
