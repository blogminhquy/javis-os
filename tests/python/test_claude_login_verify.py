"""Signing in to Claude from the Models page only says yes when the CLI really is signed in (0.383.0).

    python tests/run.py claude_login_verify      (no network: a fake `claude` stands in for the CLI)

Why this file exists: `claude auth login` prints "Login successful." and exits 0 even when it could not SAVE the
credentials (on a Mac they go to the Keychain). Javis believed that line, told the card the sign-in worked, and the
card's own check then read "Not signed in" with no reason given. A customer on a MacBook tried 4-5 times
(28/10/2026). Also pinned: a bare "logged in" no longer counts as success (it matched "not logged in"), and a wrong
code followed by a right one is not answered with the first code's error.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
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

_TMP = Path(tempfile.mkdtemp(prefix="javis-claude-login-"))
_STATE = _TMP / "main-state"
_FAKE = _TMP / "claude"
# auth login: prints like the real 2.1.x CLI, then reads codes. "good#s" saves and succeeds, "nosave#s" says
# success WITHOUT saving (the Keychain case), "wrong#s" is refused and exits 1, a code with no "#" is rejected
# and the CLI keeps waiting. auth status: signed in when the state file exists.
_FAKE.write_text(f"""#!{sys.executable}
import json, os, sys
state = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "state") if os.environ.get("CLAUDE_CONFIG_DIR") \\
    else {str(_STATE)!r}
if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": os.path.exists(state), "email": "a@b.c", "subscriptionType": "max"}}))
    sys.exit(0)
if sys.argv[1:3] == ["auth", "login"]:
    print("Opening browser to sign in\\u2026", flush=True)
    print("If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=s", flush=True)
    sys.stdout.write("Paste code here if prompted > "); sys.stdout.flush()
    for line in sys.stdin:
        code = line.strip()
        if "#" not in code:
            sys.stderr.write("Invalid code. Please make sure the full code was copied.\\n"); sys.stderr.flush()
            continue
        if code == "good#s":
            open(state, "w").close()
            print("Login successful.", flush=True); sys.exit(0)
        if code == "nosave#s":
            print("Login successful.", flush=True); sys.exit(0)
        sys.stderr.write("Login failed: That code wasn't accepted.\\n"); sys.stderr.flush(); sys.exit(1)
sys.exit(2)
""", encoding="utf-8")
_FAKE.chmod(_FAKE.stat().st_mode | stat.S_IEXEC)
claude_cli.find_claude_cli = lambda: str(_FAKE)


def start(env=None):
    claude_cli.auth_quen_cache()
    d = claude_cli.auth_login_ui_start(env)
    check("the sign-in link comes back", d.get("ok") and d.get("url", "").startswith("https://claude.com/"))
    return d


# ---- 1. The CLI says success but saved nothing: the card must hear why, not a silent yes ----
_STATE.unlink(missing_ok=True)
start()
r = claude_cli.auth_login_ui_code("nosave#s")
check("success line without saved credentials -> ok False", r.get("ok") is False)
check("the error says the sign-in was not saved", "claude auth login" in (r.get("error") or ""))
check("the error has no em dash", "—" not in (r.get("error") or ""))

# ---- 2. A real sign-in still goes through, and the card's cache is fresh ----
_STATE.unlink(missing_ok=True)
start()
r = claude_cli.auth_login_ui_code("good#s")
check("a saved sign-in -> ok True", r.get("ok") is True)
check("the card reads signed in right away (no stale 'not signed in' cache)",
      claude_cli.auth_status().get("connected") is True)

# ---- 3. A malformed code, then the right one: the first error must not answer the second ----
_STATE.unlink(missing_ok=True)
start()
r1 = claude_cli.auth_login_ui_code("nohash")
check("malformed code -> the CLI's own reason", r1.get("ok") is False and "Invalid code" in (r1.get("error") or ""))
r2 = claude_cli.auth_login_ui_code("good#s")
check("the next, right code signs in", r2.get("ok") is True)

# ---- 4. A refused code ends the CLI; the reason reaches the card ----
_STATE.unlink(missing_ok=True)
start()
r = claude_cli.auth_login_ui_code("wrong#s")
check("refused code -> ok False with the CLI's reason", r.get("ok") is False and "accepted" in (r.get("error") or ""))
r = claude_cli.auth_login_ui_code("good#s")
check("pasting into an ended sign-in asks for a new link", r.get("ok") is False and r.get("error"))

# ---- 5. An extra plan account verifies against ITS folder, not the machine's login ----
_STATE.unlink(missing_ok=True)
_acc = _TMP / "acc2"
_acc.mkdir()
start({"CLAUDE_CONFIG_DIR": str(_acc)})
r = claude_cli.auth_login_ui_code("good#s")
check("extra account saved in its folder -> ok True", r.get("ok") is True)
check("the machine's own login was not touched", not _STATE.exists())

# ---- 6. Success detection no longer matches "not logged in" ----
check("'Not logged in' is not success", not claude_cli._login_line_done("not logged in. run claude auth login"))
check("'Login successful.' is success", claude_cli._login_line_done("login successful."))

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
