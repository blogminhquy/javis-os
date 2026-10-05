"""The admin password set in the environment (JAVIS_ADMIN_PASSWORD) must actually work.

    python tests/run.py admin_env_password      (no network)

Real report (2026-10-05, a Hostinger customer): they typed exactly the username and password
set in the Hostinger Environment box and still got "Wrong username or password". Root cause:
the env password was only used when NO admin existed yet. Once an admin was there (created on
the setup screen, or from an older env value), changing the env and redeploying did nothing at
all, silently. On a VPS that was also the only realistic way to reset a forgotten password.

Contract now:
1. No admin yet + env set -> create the admin (unchanged behaviour).
2. Admin exists and the env value CHANGED since it was last applied -> apply it (reset).
   2FA stays, other sessions are dropped like a normal password change.
3. Env unchanged across restarts -> leave the account alone, so a password changed later
   from the dashboard is not reverted on every reboot.
4. Only a salted hash of the applied env value is stored, never the value itself.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-envpw-")
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

import config as c   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def set_env(pw=None, user=None):
    for k, v in (("JAVIS_ADMIN_PASSWORD", pw), ("JAVIS_ADMIN_USER", user)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def can_login(user, pw):
    cfg = c.read_settings()
    return cfg.get("auth", {}).get("username") == user and c.verify_password(pw, cfg)


# ---- 0. No env -> nothing happens ----
set_env()
check("no env: does nothing", not c.provision_admin_from_env())
check("no env: still no admin", not c.auth_enabled())

# ---- 1. No admin + env -> created ----
set_env("first-pass-123", "admin")
check("no admin + env: reports created", c.provision_admin_from_env() == "created")
check("no admin + env: can sign in with the env password", can_login("admin", "first-pass-123"))

# ---- 2. Same env on the next boot -> no-op ----
check("same env next boot: no change", not c.provision_admin_from_env())

# ---- 3. Owner changes the password in the dashboard, env stays -> dashboard wins ----
cfg = c.read_settings()
a = dict(cfg["auth"])
a["password_hash"], a["salt"] = c.hash_password("changed-in-ui-1")
cfg["auth"] = a
c.write_settings(cfg)
check("env unchanged after a dashboard change: no reset", not c.provision_admin_from_env())
check("env unchanged: the dashboard password still works", can_login("admin", "changed-in-ui-1"))

# ---- 4. The customer's case: env CHANGED on Hostinger, redeploy -> applied ----
cfg = c.read_settings()
cfg["auth"]["totp"] = {"enabled": True, "secret": "KEEP-ME"}
c.write_settings(cfg)
sess = c.new_session()
set_env("new-hostinger-pw", "admin")
check("env changed: reports reset", c.provision_admin_from_env() == "reset")
check("env changed: the new env password works", can_login("admin", "new-hostinger-pw"))
check("env changed: the old password no longer works", not can_login("admin", "changed-in-ui-1"))
check("env changed: 2FA is kept", c.read_settings()["auth"].get("totp", {}).get("secret") == "KEEP-ME")
check("env changed: old sessions are dropped", not c.valid_session(sess))

# ---- 5. Env username changed -> applied too ----
set_env("new-hostinger-pw", "storm")
check("env username changed: reports reset", c.provision_admin_from_env() == "reset")
check("env username changed: new username signs in", can_login("storm", "new-hostinger-pw"))

# ---- 6. Upgrade from an older version: admin exists, no record of what env was applied ----
cfg = c.read_settings()
h, s = c.hash_password("legacy-pass-99")
cfg["auth"] = {"username": "admin", "password_hash": h, "salt": s}   # no env marker
c.write_settings(cfg)
sess = c.new_session()
set_env("legacy-pass-99", "admin")
check("upgrade, env equals current password: no reset", not c.provision_admin_from_env())
check("upgrade, env equals current password: sessions kept", c.valid_session(sess))
set_env("legacy-pass-99", "admin")
check("upgrade, then same env again: still no reset", not c.provision_admin_from_env())

cfg = c.read_settings()
h, s = c.hash_password("set-on-setup-screen")
cfg["auth"] = {"username": "admin", "password_hash": h, "salt": s}
c.write_settings(cfg)
set_env("typed-on-hostinger", "admin")
check("upgrade, env differs from the setup-screen password: reset",
      c.provision_admin_from_env() == "reset")
check("upgrade, env differs: the env password works", can_login("admin", "typed-on-hostinger"))

# ---- 7. Never store the env value itself ----
raw = (c.STATE_DIR / "settings.json").read_text(encoding="utf-8")
check("the env password is not stored in plain text", "typed-on-hostinger" not in raw)
check("an applied-env marker is stored", "env_applied" in json.dumps(c.read_settings().get("auth", {})))

# ---- 8. Login screen has a show/hide password button ----
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("login screen has a show-password toggle", 'id="authPassEye"' in html)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All admin_env_password tests passed.")
