"""Assistant name in live status lines follows workspace_name. Run:

    python tests/run.py ten_tro_ly

No network. Default workspace name keeps the old "Javis" wording; a renamed workspace shows
its own name in the "is thinking" / "double-checking" / "answering quickly" status lines.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tentroly-")

import main              # noqa: E402
import config as cfgmod  # noqa: E402
import localefmt         # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def set_name(value):
    cfg = cfgmod.read_settings()
    cfg["workspace_name"] = value
    cfgmod.write_settings(cfg)


def thinking():
    return localefmt.chu("{ten} đang suy nghĩ...", "{ten} is thinking...", ten=main._assistant_name())


set_name("Javis OS")
check("default workspace name reads as Javis", main._assistant_name() == "Javis")
check("default status line unchanged", "Javis" in thinking())

set_name("Kyan")
check("renamed workspace is used", main._assistant_name() == "Kyan")
check("status line carries the new name", "Kyan" in thinking() and "Javis" not in thinking())

set_name("  ")
check("blank name falls back to Javis", main._assistant_name() == "Javis")

set_name("Ky{an}")
check("braces in the name do not break the line", "Ky{an}" in thinking())

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("no hard-coded 'Javis đang suy nghĩ' left in the chat status", 'chu("Javis đang suy nghĩ' not in src)

raise SystemExit(1 if _fails else 0)
