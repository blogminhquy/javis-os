"""The code box when signing in to Claude is wide enough to read (0.308.0).

    python tests/run.py o_ma_claude

Owner screenshot 24/10/2026: the box was 24px wide. The row was a bare flex div, and the global .gcard-btn rule (width:
100%, declared after the narrow one) let the button take the whole row. Measured in Chromium before the fix: 24px on a
1280px and a 390px screen; after: 425px and 328px. This file keeps the pieces that make it so.
"""
from _paths import ROOT  # noqa: F401
import re
import sys

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
i = js.find('id="cliCode"')
row = js[js.rfind("<div", 0, i):i]
check("the code row is a .prov-action row (button sized to its text)", 'class="prov-action prov-code"' in row, row)
check("no inline flex:1 that lets the button win", 'style="flex:1"' not in js[i:i + 300])
check(".prov-action keeps buttons narrow", ".prov-action .gcard-btn { width: auto; flex: 0 0 auto;" in css)
m = re.search(r"\.prov-code \.js-input \{([^}]*)\}", css)
rule = m.group(1) if m else ""
check("the box grows, never shrinks below its text, wraps the button under on a phone",
      "flex: 1 1 240px" in rule and "min-width: 0" in rule, rule)
check("16px text (no iOS zoom, readable)", "font-size: 16px" in rule, rule)
check("no autocorrect on a code", 'autocapitalize="off"' in js[i:i + 400] and 'spellcheck="false"' in js[i:i + 400])
body = js[js.find('const cb = el.querySelector("#cliCodeBtn");'):js.find("// ---- ChatGPT OAuth device-code")]
check("Enter sends", 'e.key === "Enter"' in body)
check("stray spaces and line breaks are removed from the pasted code", ".replace(/\\s+/g, \"\")" in body, body[:400])
check("empty code: says what to do instead of sending", "models.code_empty" in body)
check("button locked while confirming", "cb.disabled = true" in body and "cb.disabled = false" in body)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
