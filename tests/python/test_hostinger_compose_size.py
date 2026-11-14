"""docker-compose.hostinger.yml stays small enough for hPanel's compose editor.

Run: python tests/run.py hostinger_compose_size

Owner report 2026-11-14: hPanel's compose editor refused to Deploy, even after a one-line edit,
because the file had grown to 33,167 characters against a limit of 32,768. The `guard` service
(0.557.1) had added a full inline copy of docker/guard.py with all its docstrings and comments.

The fix inlines a compact copy (tools/sync_guard.py). This test keeps the file under the limit
with room left for the installer's own edits in that editor (a domain in the Traefik labels, a
port, a name). It counts both characters and UTF-8 bytes: Hostinger does not publish which one it
measures, and the Vietnamese comments make the byte count the larger of the two.

Over budget? Shorten comments in docker-compose.hostinger.yml (the long explanations belong in
docs/ or in docker/guard.py), never the settings themselves.
"""
from _paths import ROOT  # noqa: E402,F401
import sys

FAIL = []


def check(label, ok):
    print(("PASS" if ok else "FAIL") + ": " + label)
    if not ok:
        FAIL.append(label)


HPANEL_LIMIT = 32768           # characters hPanel's compose editor accepts before it blocks Deploy
EDIT_ROOM = 2048               # kept free for what the installer types into that editor
BUDGET = HPANEL_LIMIT - EDIT_ROOM

text = (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
chars, size = len(text), len(text.encode("utf-8"))
print(f"docker-compose.hostinger.yml: {chars} characters, {size} bytes (budget {BUDGET})")
check(f"under hPanel's {HPANEL_LIMIT} characters", chars <= HPANEL_LIMIT)
check(f"under {HPANEL_LIMIT} bytes too", size <= HPANEL_LIMIT)
check(f"leaves {EDIT_ROOM} for the installer's edits, counted in characters", chars <= BUDGET)
check(f"leaves {EDIT_ROOM} for the installer's edits, counted in bytes", size <= BUDGET)

if FAIL:
    print("\nFAILED:", ", ".join(FAIL))
    print("Shorten comments in docker-compose.hostinger.yml; see this file's docstring.")
    sys.exit(1)
print("\nOK - test_hostinger_compose_size: all passed")
