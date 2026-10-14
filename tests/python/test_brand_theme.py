"""Operator theme at STATE_DIR/branding/theme.css. Run:

    python tests/run.py brand_theme

No network. Covers: no file = page unchanged, file present = <link> after the bundled
stylesheets with a content hash, default-mode marker seeds localStorage before the inline
theme script, the route serves the file and is public (login screen is themed too).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

# Always a fresh temp dir: this test deletes branding/theme.css, and with an inherited
# JAVIS_STATE_DIR it would delete a real operator theme.
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-themetest-")

import main              # noqa: E402
import config as cfgmod  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def page():
    return asyncio.run(main.root()).body.decode("utf-8")


theme = cfgmod.BRANDING_DIR / "theme.css"
if theme.exists():
    theme.unlink()

html = page()
check("no theme file -> no theme link", "/brand-theme.css" not in html)

cfgmod.BRANDING_DIR.mkdir(parents=True, exist_ok=True)
theme.write_text(":root{--accent:#33B560}", encoding="utf-8")
html = page()
i_link = html.find('href="/brand-theme.css?v=')
check("theme link injected", i_link > 0)
check("theme loads after bundled css", i_link > html.find("/static/console.css"))
check("no default-mode seed without marker", "localStorage.setItem('javis.theme'" not in html)

v1 = html[i_link:i_link + 40]
theme.write_text(":root{--accent:#1D3F4F}", encoding="utf-8")
check("hash changes with content", page()[i_link:i_link + 40] != v1)

theme.write_text("/* javis-default-mode: light */\n:root{}", encoding="utf-8")
html = page()
i_seed = html.find("localStorage.setItem('javis.theme','light')")
i_inline = html.find("localStorage.getItem('javis.theme')", i_seed + 1)
check("default-mode seed injected", i_seed > 0)
check("seed runs before inline theme script", 0 < i_seed < i_inline)

resp = asyncio.run(main.brand_theme_css())
check("route serves css", getattr(resp, "media_type", "") == "text/css")
check("route is public", "/brand-theme.css" in main._AUTH_PUBLIC_EXACT)

theme.write_bytes(b"x" * (main._BRAND_THEME_MAX_BYTES + 1))
check("oversized file ignored", "/brand-theme.css" not in page())
theme.unlink()

if _fails:
    raise SystemExit(f"{len(_fails)} failed")
print("all ok")
