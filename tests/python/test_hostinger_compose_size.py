"""docker-compose.hostinger.yml stays small enough for hPanel's compose editor.

Run: python tests/run.py hostinger_compose_size

Owner report 2026-11-14: hPanel's compose editor refused to Deploy, even after a one-line edit,
because the file had grown to 33,167 characters against a limit of 32,768. The `guard` service
(0.557.1) had added a full inline copy of docker/guard.py with all its docstrings and comments.

The fix inlines a compact copy (tools/sync_guard.py). This test keeps the file under the limit
with room left for the installer's own edits in that editor (a domain in the Traefik labels, a
port, a name). Hostinger does not publish what it measures, so every plausible way of counting must
fit: characters, UTF-8 bytes, and the text once it is encoded for transport.

Owner report 2026-11-21: the Hostinger link failed again while docker-compose.yml deployed fine.
The file was 28,386 characters then, under the limit, but 35,485 once JSON-encoded: an encoder
that escapes non-ASCII writes every Vietnamese letter as six characters. The comments are now
English and ASCII only, and this test also counts the encoded forms.

Over budget? Shorten comments in docker-compose.hostinger.yml (the long explanations belong in
docs/dev/hostinger-compose.md or in docker/guard.py), never the settings themselves.
"""
from _paths import ROOT  # noqa: E402,F401
import json
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

# Encoded for transport. JSON as JavaScript writes it keeps non-ASCII; as PHP writes it by default,
# non-ASCII becomes \uXXXX and every "/" becomes "\/". The quotes around the string are not counted.
js_json = len(json.dumps(text, ensure_ascii=False)) - 2
php_json = len(json.dumps(text, ensure_ascii=True)) - 2 + text.count("/")
print(f"JSON-encoded: {js_json} (non-ASCII kept), {php_json} (non-ASCII and slashes escaped)")
check(f"leaves {EDIT_ROOM} for the installer's edits, JSON-encoded", js_json <= BUDGET)
check(f"leaves {EDIT_ROOM} for the installer's edits, JSON-encoded with non-ASCII and slashes escaped",
      php_json <= BUDGET)
non_ascii = sorted({c for c in text if ord(c) > 127})
check("ASCII only (an escaped non-ASCII character costs six)", not non_ascii)
if non_ascii:
    print("non-ASCII characters:", "".join(non_ascii[:40]))

if FAIL:
    print("\nFAILED:", ", ".join(FAIL))
    print("Shorten comments in docker-compose.hostinger.yml; see this file's docstring.")
    sys.exit(1)
print("\nOK - test_hostinger_compose_size: all passed")
