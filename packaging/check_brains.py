#!/usr/bin/env python3
"""Check that the four subscription brains are installed, the way Javis itself sees them.

    <install dir>/.venv/bin/python packaging/check_brains.py      (Windows: .venv\\Scripts\\python.exe)

Uses the server's own finders (PATH plus the vendor install folders it also searches), so a
CLI that the installer put somewhere off PATH still counts when Javis would find it, and one
Javis would miss fails here. The desktop-installers workflow runs it after a fresh install.
Exit code 1 lists what is missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from antigravity_cli import find_antigravity_cli  # noqa: E402
from claude_cli import find_claude_cli, find_codex_cli  # noqa: E402
from grok_cli import find_grok_cli  # noqa: E402

BRAINS = (
    ("Claude Code", find_claude_cli),
    ("Codex (ChatGPT)", find_codex_cli),
    ("Antigravity CLI", find_antigravity_cli),
    ("Grok Build", find_grok_cli),
)


def main() -> int:
    missing = []
    for name, finder in BRAINS:
        path = finder()
        print(f"{'ok     ' if path else 'MISSING'} {name}: {path or '-'}")
        if not path:
            missing.append(name)
    if missing:
        print("Missing: " + ", ".join(missing))
        return 1
    print("All four brains installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
