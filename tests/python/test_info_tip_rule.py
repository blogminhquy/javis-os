"""Rule (owner, 2026-10-18): a long explanation on screen folds into the (i) button.

"hiện tại có quá nhiều dòng giải thích, anh muốn các dòng giải thích đấy gọn lại trong chữ (i) chứ không để xổ hết ra
bên ngoài". The rule lives in docs/quy-uoc-dev.md ("Chữ giải thích gập vào nút (i)"); this file enforces it.

Every dashboard string longer than LIMIT characters (Vietnamese text) that a page renders must either
- sit inside the (i) block: passed to `JavisInfo.body(...)` / `JavisInfo.pair(...)`, or inside an element with class
  `info-body` in index.html, or
- be listed in ALLOW below with the reason it is not an explanation (an error or confirm text shown after an action,
  a placeholder, content the user reads on purpose).

Strings that come from the server (plugin and channel descriptions) are checked at their renderers.

    python tests/python/test_info_tip_rule.py            # check
    python tests/python/test_info_tip_rule.py --report   # list every offending reference by file
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
LIMIT = 100

# key -> why it may stay on screen. Keep the reason honest: "error", "confirm", "toast", "placeholder", "status"
# (a result shown after the user acts), "content" (text the user opened on purpose, e.g. a prompt or a dialog body).
ALLOW = json.loads((Path(__file__).with_name("info_tip_allow.json")).read_text(encoding="utf-8"))

# `dam` = star-nudge.js: t() plus **bold**, so its long strings are checked like any other.
REF = re.compile(r'(?:\b(?:t|tw|tt|T|tr|L|dam)\(\s*|data-i18n(?:-html)?=)"([A-Za-z0-9_.]+)"')
# The (i) helpers as modules call them: JavisInfo.body/pair directly, a local alias (JI, J), or the module's own
# infoBody/infoPair wrapper (which falls back to drawing the text open when info-tip.js is absent, as in Node tests).
WRAP = ("JavisInfo.body(", "JavisInfo.pair(", "JI.body(", "JI.pair(", "J.body(", "J.pair(", "infoBody(", "infoPair(",
        'class="info-body"', "class='info-body'")

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


vi = json.loads((DASH / "i18n" / "vi.json").read_text(encoding="utf-8"))
long_keys = {k for k, v in vi.items() if len(v) > LIMIT}


def wrapped(src: str, pos: int) -> bool:
    """True when the reference at `pos` is an argument of a (i) helper or inside an info-body element."""
    before = src[max(0, pos - 400):pos]
    best = max(before.rfind(w) for w in WRAP)
    if best < 0:
        return False
    # A closing tag of the block or the end of a JS statement between the helper and the reference ends the block.
    tail = before[best:]
    if 'class="info-body"' in tail[:20] or "class='info-body'" in tail[:20]:
        return "</div>" not in tail
    return ";\n" not in tail and "})" not in tail


offenders = {}
files = sorted(DASH.glob("*.js")) + [DASH / "index.html"]
for f in files:
    src = f.read_text(encoding="utf-8", errors="ignore")
    for m in REF.finditer(src):
        k = m.group(1)
        if k not in long_keys or k in ALLOW:
            continue
        if wrapped(src, m.start()):
            continue
        offenders.setdefault(f.name, []).append(k)

if "--report" in sys.argv:
    total = 0
    for name, ks in sorted(offenders.items(), key=lambda x: -len(x[1])):
        print(f"{name}: {len(ks)}")
        for k in ks:
            print(f"    {k}  ({len(vi[k])})")
        total += len(ks)
    print(f"\n{total} references in {len(offenders)} files")
    sys.exit(0)

check(f"every dashboard string over {LIMIT} characters is folded into (i) or allowed with a reason",
      not offenders, "; ".join(f"{n}: {', '.join(sorted(set(k)))}" for n, k in offenders.items())[:1500])
check("allowlist names only real long keys", all(k in long_keys for k in ALLOW),
      ", ".join(k for k in ALLOW if k not in long_keys))
check("allowlist reasons are from the fixed set",
      all(v.split(":")[0] in {"error", "confirm", "toast", "placeholder", "status", "content"} for v in ALLOW.values()))

# ---- The helper and its styles ----
tip = (DASH / "info-tip.js").read_text(encoding="utf-8")
check("JavisInfo has btn, body and pair", all(f"{n}: {n}" in tip for n in ("btn", "body", "pair")))
css = (DASH / "style.css").read_text(encoding="utf-8")
m = re.search(r"\.info-body \{[^}]*font-size: (\d+)px", css)
check("the opened explanation is at least 16px", m is not None and int(m.group(1)) >= 16, m and m.group(1))
check("no smaller size on phones", "@media (max-width: 600px) { .info-body { font-size: 14px; } }" not in css)

# ---- The rule is written down ----
rules = (ROOT / "docs" / "quy-uoc-dev.md").read_text(encoding="utf-8")
check("docs/quy-uoc-dev.md carries the rule", "Chữ giải thích gập vào nút (i)" in rules and "test_info_tip_rule.py" in rules)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_info_tip_rule: all pass")
