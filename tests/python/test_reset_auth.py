"""Forgot the current password: reset-auth clears it, the Account page points at the right way back.

    python tests/run.py reset_auth      (no network, nothing is launched)

Owner request 2026-11-20: under "Change password" on the Account page, a "Forgot your current password?" link. On a
Windows or Mac install used from that computer it opens the folder with the reset file selected; on a VPS it shows
the steps. The reset clears the password for good ("coi như mất mật khẩu kia luôn") and the owner sets a new one.

Pinned here:
1. tools/reset_auth.py empties `auth` (password and 2FA) but keeps setup_done and every other setting, so the
   first-run wizard (which would ask for the AI brain again) does not come back.
2. It removes JAVIS_ADMIN_PASSWORD / JAVIS_ADMIN_USER from .env: install.sh writes them on macOS, and leaving them
   would bring the old password back at the next start (provision_admin_from_env).
3. It never writes over a settings.json it could not read.
4. GET /auth/reset-help offers the button only to a browser on this machine; POST /auth/reset-help/open only REVEALS
   the script (never runs it) and refuses tunnels and other machines.
5. Both launchers call the tool, and the .command is executable.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-resetauth-")
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

sys.path.insert(0, str(ROOT / "tools"))
import reset_auth  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


# ---- 1-3. the tool ----
state = Path(tempfile.mkdtemp(prefix="javis-reset-state-"))
settings = state / "settings.json"
before = {"setup_done": True, "workspace_name": "Shop", "model": {"engine": "codex"},
          "auth": {"username": "quy", "password_hash": "ab" * 32, "salt": "cd" * 16,
                   "totp": {"enabled": True, "secret": "enc:xyz"}, "env_applied": {"hash": "x"}}}
settings.write_text(json.dumps(before), encoding="utf-8")
env = state / ".env"
env.write_text('ANTHROPIC_API_KEY="k"\nJAVIS_ADMIN_USER="admin"\nexport JAVIS_ADMIN_PASSWORD="old pass"\n'
               "JAVIS_ADMIN_PASSWORD_HINT=keep\n", encoding="utf-8")

rc = reset_auth.main(["--state-dir", str(state), "--env-file", str(env)])
after = json.loads(settings.read_text(encoding="utf-8"))
check("tool exits 0", rc == 0, rc)
check("auth block is empty (password, username and 2FA gone)", after.get("auth") == {}, after.get("auth"))
check("setup_done and other settings are kept",
      after.get("setup_done") is True and after.get("workspace_name") == "Shop" and after.get("model") == {"engine": "codex"})
env_after = env.read_text(encoding="utf-8")
check("admin lines removed from .env, export form included",
      "JAVIS_ADMIN_PASSWORD=" not in env_after.replace("JAVIS_ADMIN_PASSWORD_HINT=", "")
      and "JAVIS_ADMIN_USER" not in env_after, env_after)
check("other .env lines are kept", 'ANTHROPIC_API_KEY="k"' in env_after and "JAVIS_ADMIN_PASSWORD_HINT=keep" in env_after)
check("no temp file left behind", not [p for p in state.iterdir() if p.name.endswith(".tmp")])

settings.write_text("{not json", encoding="utf-8")
rc = reset_auth.main(["--state-dir", str(state), "--env-file", str(env)])
check("unreadable settings.json: exits 1 and is left as it was",
      rc == 1 and settings.read_text(encoding="utf-8") == "{not json")
check("missing settings.json: exits 1", reset_auth.main(["--state-dir", str(state / "nope")]) == 1)

# The real loader agrees: an emptied account means no login and no admin to restore.
import config as c  # noqa: E402
c.SETTINGS_PATH.write_text(json.dumps(clear := reset_auth.clear_auth(before)), encoding="utf-8")
check("Javis reads the cleared file as 'no password yet'", not c.auth_enabled(c.read_settings()))
check("and still as an installed machine (no first-run wizard)", c._da_cai_dat(clear))
check("no env left -> nothing re-provisioned at boot", c.provision_admin_from_env() == "")

# ---- 4. the endpoints ----
import local_open  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

launched = []
local_open.launch = lambda action, target: launched.append((action, target))
local_open.can_launch = lambda: True
main.cfgmod.gate_active = lambda: False
check("state dir outside <repo>/server: the script would miss it, so no button",
      main._reset_script("windows") is None and main._reset_script("linux") is None)
main._reset_kind = lambda: "windows"
script = ROOT / "reset-auth.bat"
main._reset_script = lambda kind: script if kind == "windows" else None

local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))
remote = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("203.0.113.9", 50000))

r = local.get("/auth/reset-help")
check("this computer: the button is offered", r.status_code == 200 and r.json().get("can_open") is True
      and r.json().get("file") == "reset-auth.bat", r.text)
r = remote.get("/auth/reset-help")
check("another machine: steps only", r.status_code == 200 and r.json().get("can_open") is False, r.text)
r = local.get("/auth/reset-help", headers={"cf-connecting-ip": "198.51.100.7"})
check("through a tunnel: steps only", r.json().get("can_open") is False, r.text)

r = local.post("/auth/reset-help/open")
check("open REVEALS the script, never runs it", r.status_code == 200 and launched[-1] == ("reveal", script), r.text)
n = len(launched)
check("open from another machine: 403", remote.post("/auth/reset-help/open").status_code == 403 and len(launched) == n)
check("open through a tunnel: 403",
      local.post("/auth/reset-help/open", headers={"x-forwarded-for": "198.51.100.7"}).status_code == 403
      and len(launched) == n)
main._reset_kind = lambda: "docker"
r = local.get("/auth/reset-help")
check("docker: kind reported, no button", r.json().get("kind") == "docker" and r.json().get("can_open") is False, r.text)
check("docker: open refused", local.post("/auth/reset-help/open").status_code == 404 and len(launched) == n)

# ---- 5. the launchers ----
bat = (ROOT / "reset-auth.bat").read_bytes()
check("reset-auth.bat runs tools\\reset_auth.py", b"tools\\reset_auth.py" in bat)
check("reset-auth.bat keeps CRLF", b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b""))
cmd = ROOT / "reset-auth.command"
check("reset-auth.command runs tools/reset_auth.py", "tools/reset_auth.py" in cmd.read_text(encoding="utf-8"))
mode = subprocess.run(["git", "ls-files", "-s", "reset-auth.command"], cwd=ROOT, capture_output=True, text=True).stdout
check("reset-auth.command is executable in git (Finder runs it on double click)", mode.startswith("100755"), mode)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_reset_auth: all pass")
