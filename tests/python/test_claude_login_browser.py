"""Signing in to Claude in the browser, with no code to paste, finishes the Models card on its own (0.438.7).

    python tests/run.py claude_login_browser      (no network: a fake `claude` stands in for the CLI)

Why this file exists: on a machine with a browser, `claude auth login` opens the sign-in page itself and gets the
answer back over localhost. The page then only says "You're all set up for Claude Code" and shows NO code. The CLI
saves the login and exits, but the card kept waiting for a code and asked `/claude/status`, whose 90 s cache still
said "signed out", so the owner had to reload the page (report 02/11/2026, Windows). The card now asks
`/claude/login-poll`, which reads the sign-in process itself.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

import claude_cli   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


if os.name == "nt":
    print("skip: the fake CLI is a POSIX script")
    sys.exit(0)

_TMP = Path(tempfile.mkdtemp(prefix="javis-claude-browser-"))
_STATE = _TMP / "state"
_GO = _TMP / "browser-done"
_FAKE = _TMP / "claude"
# auth login: prints the link like the real CLI, then waits for the "browser" (a trigger file). FAKE_MODE=ok saves
# and succeeds, FAKE_MODE=fail exits 1 without saving. auth status: signed in when the state file exists.
_FAKE.write_text(f"""#!{sys.executable}
import json, os, sys, time
state, go = {str(_STATE)!r}, {str(_GO)!r}
if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": os.path.exists(state), "email": "a@b.c", "subscriptionType": "max"}}))
    sys.exit(0)
if sys.argv[1:3] == ["auth", "login"]:
    print("Opening browser to sign in\\u2026", flush=True)
    print("If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=s", flush=True)
    sys.stdout.write("Paste code here if prompted > "); sys.stdout.flush()
    while not os.path.exists(go):
        time.sleep(0.05)
    if os.environ.get("FAKE_MODE") == "fail":
        sys.stderr.write("OAuth error: access denied\\n"); sys.stderr.flush(); sys.exit(1)
    open(state, "w").close()
    print("Login successful.", flush=True); sys.exit(0)
sys.exit(2)
""", encoding="utf-8")
_FAKE.chmod(_FAKE.stat().st_mode | stat.S_IEXEC)
claude_cli.find_claude_cli = lambda: str(_FAKE)


def wait_poll(cond, secs=10.0):
    end = time.time() + secs
    d = claude_cli.auth_login_ui_poll()
    while not cond(d) and time.time() < end:
        time.sleep(0.1)
        d = claude_cli.auth_login_ui_poll()
    return d


# ---- 1. Signed in in the browser: the poll says connected, and the status cache no longer says signed out ----
_STATE.unlink(missing_ok=True)
_GO.unlink(missing_ok=True)
claude_cli.auth_quen_cache()
check("before: status says signed out", claude_cli.auth_status().get("connected") is False)
d = claude_cli.auth_login_ui_start({"FAKE_MODE": "ok"})
check("the sign-in link comes back", d.get("ok") and d.get("url", "").startswith("https://claude.com/"))
d = claude_cli.auth_login_ui_poll()
check("while the browser has not answered: waiting", d.get("waiting") is True and not d.get("connected"))
_GO.touch()
d = wait_poll(lambda x: x.get("connected") or x.get("ended"))
check("browser finished: poll says connected", d.get("connected") is True)
check("the cached status now says signed in (no reload needed)", claude_cli.auth_status().get("connected") is True)
check("asking again keeps saying connected", claude_cli.auth_login_ui_poll().get("connected") is True)

# ---- 2. The CLI exits without signing in: the poll says it ended, with the reason ----
_STATE.unlink(missing_ok=True)
_GO.unlink(missing_ok=True)
claude_cli.auth_quen_cache()
claude_cli.auth_login_ui_start({"FAKE_MODE": "fail"})
_GO.touch()
d = wait_poll(lambda x: x.get("connected") or x.get("ended"))
check("failed sign-in: poll says ended", d.get("ended") is True and not d.get("connected"))
check("failed sign-in: the CLI's reason is passed on", "access denied" in (d.get("error") or ""))
check("the error has no em dash", "—" not in (d.get("error") or ""))

# ---- 3. No sign-in started: nothing to wait for ----
claude_cli._LOGIN["proc"] = None
d = claude_cli.auth_login_ui_poll()
check("no sign-in: not waiting, not connected", not d.get("waiting") and not d.get("connected"))

# ---- 4. The card asks the sign-in process, not the cached status, and asks again when the user comes back ----
js = (Path(ROOT) / "dashboard" / "console.js").read_text(encoding="utf-8")
i = js.index("async function startClaudeLogin")
body = js[i:js.index("\n  }\n", i)]
check("the card polls /claude/login-poll", "/claude/login-poll" in body)
check("the card no longer polls the cached /claude/status", '"/claude/status"' not in body)
check("the card asks again when the tab gets focus", '"focus"' in body and "visibilitychange" in body)
main = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the server has /claude/login-poll", '@app.get("/claude/login-poll")' in main)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
