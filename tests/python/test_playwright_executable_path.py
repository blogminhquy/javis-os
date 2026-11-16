"""The Playwright connection must run on the browser Javis downloaded, whatever its revision.

    python tests/run.py playwright_executable_path

Real failure, reported 16/11/2026 from a team chat: every Playwright tool call died with

    Browser "chrome-for-testing" is not installed; expected executable at
    /data/state/browsers/chromium-1254/chrome-linux64/chrome

The connector runs `npx -y @playwright/mcp@latest` (0.0.85 that day, built on playwright-core
1.66.0-alpha, which wants the FULL build `chromium-1254`). Javis's own download button runs
`npx -y playwright@latest install --only-shell chromium` (1.65.1 that day), which fetches the
headless shell `chromium_headless_shell-1255` and garbage-collects every build no registered
Playwright version still references, `chromium-1254` included. Two packages released on their own
schedule, two different revisions, and the MCP never falls back to a headless shell by itself.

Fix: Javis tells the MCP exactly which file to run (PLAYWRIGHT_MCP_EXECUTABLE_PATH) when it drives
Chromium and Javis has downloaded one. Proven by hand on that machine: with the variable the same
MCP 0.0.85 navigates and screenshots on `chromium_headless_shell-1255`.

What this file holds:
  1. A Playwright connection on a machine with only Javis's headless shell gets that file.
  2. A full build wins over the headless shell when both are there.
  3. Javis never overrides a browser the user chose: another browser, their own executable path,
     a CDP endpoint, a browser flag in the args, a config file.
  4. A headless shell is not handed over when the user asked to SEE the window (it cannot show one).
  5. No download, no variable; a connection that is not Playwright gets nothing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pwexe-")

import mcp_store  # noqa: E402
import optional_tools as ot  # noqa: E402

KEY = "PLAYWRIGHT_MCP_EXECUTABLE_PATH"
SHELL = "chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell"
FULL = "chromium-1254/chrome-linux64/chrome"

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if not cond and them else ""))
    if not cond:
        _fails.append(name)


def builds(*rel):
    """Lay out fake browser builds under BROWSERS_DIR, replacing whatever was there."""
    shutil.rmtree(ot.BROWSERS_DIR, ignore_errors=True)
    for r in rel:
        p = ot.BROWSERS_DIR / r
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    return [str(ot.BROWSERS_DIR / r) for r in rel]


def env_of(args=None, env=None, command="npx"):
    """Resolved env of a fresh Playwright connection, then remove it again."""
    cid, err = mcp_store.add_connection("custom", {
        "label": "pw-test", "transport": "stdio", "command": command,
        "args": ["-y", "@playwright/mcp@latest"] if args is None else args,
        "env": env or {}})
    assert cid, err
    try:
        row = next(r for r in mcp_store.resolved(enabled_only=False) if r["id"] == cid)
        return row["env"]
    finally:
        mcp_store.delete_connection(cid)


# ---- 1. only the headless shell Javis downloaded ----
shell, = builds(SHELL)
e = env_of()
check("headless shell only: the connection gets the executable path", e.get(KEY) == shell, str(e.get(KEY)))
check("headless shell only: the browsers folder is still passed", e.get(ot.ENV_BROWSERS_PATH) == str(ot.BROWSERS_DIR))
e = env_of(env={"PLAYWRIGHT_MCP_BROWSER": "chromium", "PLAYWRIGHT_MCP_HEADLESS": "true"})
check("user typed chromium (the advice given on 16/11): still gets the path", e.get(KEY) == shell, str(e.get(KEY)))

# ---- 2. full build preferred ----
full, shell = builds(FULL, SHELL)
e = env_of()
check("full build and headless shell: the full build is used", e.get(KEY) == full, str(e.get(KEY)))
e = env_of(env={"PLAYWRIGHT_MCP_HEADLESS": "false"})
check("full build can show a window: still passed when headless is off", e.get(KEY) == full, str(e.get(KEY)))

# ---- 3. a browser the user chose is never overridden ----
shell, = builds(SHELL)
for name, kw in [
    ("browser firefox", {"env": {"PLAYWRIGHT_MCP_BROWSER": "firefox"}}),
    ("browser chrome", {"env": {"PLAYWRIGHT_MCP_BROWSER": "chrome"}}),
    ("CDP endpoint", {"env": {"PLAYWRIGHT_MCP_CDP_ENDPOINT": "http://127.0.0.1:9222"}}),
    ("remote endpoint", {"env": {"PLAYWRIGHT_MCP_ENDPOINT": "ws://127.0.0.1:3000"}}),
    ("browser extension", {"env": {"PLAYWRIGHT_MCP_EXTENSION": "true"}}),
    ("config file", {"env": {"PLAYWRIGHT_MCP_CONFIG": "/tmp/pw.json"}}),
    ("--browser in args", {"args": ["-y", "@playwright/mcp@latest", "--browser", "chromium"]}),
    ("--browser= in args", {"args": ["-y", "@playwright/mcp@latest", "--browser=msedge"]}),
    ("--executable-path in args", {"args": ["-y", "@playwright/mcp@latest", "--executable-path", "/opt/c"]}),
    ("--cdp-endpoint in args", {"args": ["-y", "@playwright/mcp@latest", "--cdp-endpoint=http://x:9222"]}),
    ("--extension in args", {"args": ["-y", "@playwright/mcp@latest", "--extension"]}),
    ("--config in args", {"args": ["-y", "@playwright/mcp@latest", "--config", "/tmp/pw.json"]}),
]:
    e = env_of(**kw)
    check(f"user chose their own browser ({name}): no executable path added", KEY not in e, str(e.get(KEY)))
e = env_of(env={KEY: "/opt/my/chrome"})
check("user's own executable path is kept", e.get(KEY) == "/opt/my/chrome", str(e.get(KEY)))

# ---- 4. headless shell cannot show a window ----
for off in ("false", "0", "no", "FALSE"):
    e = env_of(env={"PLAYWRIGHT_MCP_HEADLESS": off})
    check(f"headless={off} with only a headless shell: not handed over", KEY not in e, str(e.get(KEY)))

# ---- 5. nothing to point at, or not Playwright ----
builds()
e = env_of()
check("no download: no executable path", KEY not in e, str(e.get(KEY)))
builds(SHELL)
e = env_of(args=["-y", "some-other-mcp"], command="npx")
check("a connection that is not Playwright gets nothing", KEY not in e, str(e.get(KEY)))

# ---- the helper on its own, for callers other than mcp_store ----
full, = builds(FULL)
check("executable_env answers on a plain env", ot.executable_env({}) == {KEY: full}, str(ot.executable_env({})))
check("executable_env reads a browser flag from args", ot.executable_env({}, ["--browser", "webkit"]) == {})
check("downloaded_executable finds the build", ot.downloaded_executable() == full)
shutil.rmtree(ot.BROWSERS_DIR, ignore_errors=True)
check("downloaded_executable is empty with no download", ot.downloaded_executable() == "")

print()
print(f"{len(_fails)} failed" if _fails else "all ok")
raise SystemExit(1 if _fails else 0)
