"""ChatGPT knows its effort ladder right after a restart: Codex's own models cache is read as a fallback.

    python tests/run.py codex_models_cache        (no network, no Codex binary)

Ported from PR #1847 by tunganh0990. `codex_models.efforts_for` only knew a model's ladder after `model/list` ran in this
process, so after every restart a bot or a background job set to a rarer level (xhigh, minimal, ultra) ran at Codex's
default until someone opened the Models page. Codex writes the same ladders to `models_cache.json` in its home; that file
is now read when the live list has not run, re-read only when it changes, and never raises.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from pathlib import Path

HOME = Path(tempfile.mkdtemp(prefix="javis-codex-home-"))
os.environ["CODEX_HOME"] = str(HOME)

import codex_models as cm  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


CACHE = HOME / "models_cache.json"


def write(data, text=None):
    CACHE.write_text(text if text is not None else json.dumps(data), encoding="utf-8")


def levels(*names):
    return [{"effort": n, "description": f"{n} effort"} for n in names]


cm._EFFORTS.clear()
check("no cache file and no live list: the ladder is unknown", cm.efforts_for("gpt-5.5") == [])

write({"fetched_at": "2026-11-26T08:00:00Z", "client_version": "0.170.0", "models": [
    {"slug": "gpt-5.5", "display_name": "GPT-5.5", "supported_reasoning_levels": levels("low", "medium", "high", "xhigh")},
    {"slug": "gpt-5.5-mini", "supported_reasoning_levels": levels("minimal", "low", "medium")},
    {"slug": "no-levels", "supported_reasoning_levels": []},
    "not a model",
]})
check("the ladder comes from Codex's own cache right after a restart",
      cm.efforts_for("gpt-5.5") == ["low", "medium", "high", "xhigh"], cm.efforts_for("gpt-5.5"))
check("so a rarer level is passed through: ultra maps to the model's top rung", cm.muc_cho("gpt-5.5", "ultra") == "xhigh")
check("minimal is known for the model that has it", cm.muc_cho("gpt-5.5-mini", "minimal") == "minimal")
check("a model without levels, or not in the cache, stays unknown",
      cm.efforts_for("no-levels") == [] and cm.efforts_for("gpt-9") == [] and cm.efforts_for("") == [])

cm._EFFORTS["gpt-5.5"] = ["low", "high"]
check("the live model/list answer wins over the cache", cm.efforts_for("gpt-5.5") == ["low", "high"])
cm._EFFORTS.clear()

# Cached by mtime: same size and same mtime is not parsed again; a new mtime is.
before = CACHE.stat()
text = CACHE.read_text(encoding="utf-8").replace('"xhigh"', '"xhigg"')
CACHE.write_text(text, encoding="utf-8")
os.utime(CACHE, ns=(before.st_atime_ns, before.st_mtime_ns))
check("an unchanged file (same mtime and size) is not parsed again", cm.efforts_for("gpt-5.5")[-1] == "xhigh")
os.utime(CACHE, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))
check("a changed file is read again", cm.efforts_for("gpt-5.5")[-1] == "xhigg", cm.efforts_for("gpt-5.5"))

for label, raw in (("half-written JSON", '{"models": [{"slug": "gpt-5.5", "supported_'),
                   ("a list at the top", "[1, 2, 3]"),
                   ("models not a list", '{"models": {"slug": "gpt-5.5"}}'),
                   ("binary noise", "\x00\x01\x02")):
    write(None, raw)
    st = CACHE.stat()
    os.utime(CACHE, ns=(st.st_atime_ns, st.st_mtime_ns + 7_000_000_000))
    try:
        got = cm.efforts_for("gpt-5.5")
        check(f"{label}: no ladder, no exception", got == [], got)
    except Exception as e:  # noqa: BLE001
        check(f"{label}: no ladder, no exception", False, f"{type(e).__name__}: {e}")

CACHE.unlink()
check("the cache file removed: unknown again", cm.efforts_for("gpt-5.5") == [])
os.environ["CODEX_HOME"] = str(HOME / "missing-folder")
check("a Codex home that does not exist: unknown, no exception", cm.efforts_for("gpt-5.5") == [])

print()
print(f"RED {len(_fails)}: " + "; ".join(_fails) if _fails else "GREEN: all passed")
sys.exit(1 if _fails else 0)
