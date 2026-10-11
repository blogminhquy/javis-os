"""Signing in must not fail on things the owner cannot see: letter case in the username and
stray spaces around the password.

    python tests/run.py login_forgiving      (no network)

Real report (2026-10-11, a customer on Hostinger): "I type the right password and still cannot
get in", after resetting the password twice. Two invisible causes were possible in the code:

1. The username was compared case-sensitively. An account created as "Phong" on the setup
   screen could not sign in as "phong", and a phone keyboard capitalises the first letter on
   its own. Usernames are not secrets, so case must not matter.
2. Passwords were hashed exactly as typed. Phone keyboards add a trailing space after an
   autocompleted word, and a value pasted into the Hostinger Environment box can carry one
   too. The owner never sees that space, so it must not decide whether they get in.

Contract:
- usernames match ignoring case and surrounding spaces;
- every place that STORES a password (setup screen, password change, JAVIS_ADMIN_PASSWORD)
  stores it without surrounding whitespace;
- signing in accepts the password as typed, or without its surrounding whitespace, so an
  older hash stored with a space still works when typed exactly;
- a wrong password is still wrong, and an all-space password never matches.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-login-")
# Public-server mode, like the customer's VPS (and lets TestClient's host through the DNS-rebinding guard).
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

import config as c   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def store(username, password, raw=False):
    """Write an account straight into settings. raw=True keeps the password exactly as given,
    to stand for a hash written by an older version."""
    cfg = c.read_settings()
    pw = password if raw else c.clean_password(password)
    h, salt = c.hash_password(pw)
    cfg["auth"] = {"username": username, "password_hash": h, "salt": salt}
    c.write_settings(cfg)


# ---- 1. Username: case and surrounding spaces do not matter ----
store("Phong", "dung-mat-khau-1")
cfg = c.read_settings()
check("username: exact match", c.username_matches("Phong", cfg))
check("username: lower case typed on a phone", c.username_matches("phong", cfg))
check("username: auto-capitalised / upper case", c.username_matches("PHONG", cfg))
check("username: surrounding spaces", c.username_matches("  phong ", cfg))
check("username: a different name still fails", not c.username_matches("phong2", cfg))
check("username: empty never matches", not c.username_matches("", cfg))

# ---- 2. Password: surrounding whitespace typed by the keyboard does not matter ----
check("password: exact", c.verify_password("dung-mat-khau-1", cfg))
check("password: trailing space from autocomplete", c.verify_password("dung-mat-khau-1 ", cfg))
check("password: leading space", c.verify_password(" dung-mat-khau-1", cfg))
check("password: wrong is still wrong", not c.verify_password("sai-mat-khau-1", cfg))
check("password: inner characters still matter", not c.verify_password("dung-mat-khau-2", cfg))
check("password: all spaces never match", not c.verify_password("     ", cfg))
check("password: empty never matches", not c.verify_password("", cfg))

# ---- 3. An older hash stored WITH a space still works when typed exactly ----
store("admin", "co-dau-cach-cu ", raw=True)
cfg = c.read_settings()
check("legacy hash with a trailing space: typed exactly still works",
      c.verify_password("co-dau-cach-cu ", cfg))

# ---- 4. JAVIS_ADMIN_PASSWORD with stray whitespace (pasted into Hostinger) ----
cfg = c.read_settings()
cfg.pop("auth", None)
c.write_settings(cfg)
os.environ["JAVIS_ADMIN_PASSWORD"] = "  mat-khau-hostinger \n"
os.environ["JAVIS_ADMIN_USER"] = " admin "
check("env with whitespace: admin created", c.provision_admin_from_env() == "created")
cfg = c.read_settings()
check("env with whitespace: signs in with the clean password",
      c.username_matches("Admin", cfg) and c.verify_password("mat-khau-hostinger", cfg))
check("env with whitespace: same env next boot is a no-op", not c.provision_admin_from_env())

# An older version applied the env value WITH its whitespace. After this update the clean
# value must be applied once, so the owner can sign in without typing the invisible space.
h, salt = c.hash_password("mat-khau-cu-co-cach ")
m_salt = "abc"
cfg = c.read_settings()
cfg["auth"] = {"username": "admin", "password_hash": h, "salt": salt,
               "env_applied": {"username": "admin", "salt": m_salt,
                               "hash": c.hash_password("mat-khau-cu-co-cach ", m_salt)[0]}}
c.write_settings(cfg)
os.environ["JAVIS_ADMIN_PASSWORD"] = "mat-khau-cu-co-cach "
os.environ["JAVIS_ADMIN_USER"] = "admin"
c.provision_admin_from_env()
cfg = c.read_settings()
check("old env applied with a trailing space: clean value now signs in",
      c.verify_password("mat-khau-cu-co-cach", cfg))
check("and the next boot does not reset again", not c.provision_admin_from_env())
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

# ---- 5. The real endpoints ----
import main   # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

cfg = c.read_settings()
cfg.pop("auth", None)
c.write_settings(cfg)
cl = TestClient(main.app)
r = cl.post("/auth/setup", data={"username": "Phong", "password": "mat-khau-moi-1 "})
check(f"setup screen: account created ({r.status_code})", r.status_code == 200 and r.json().get("ok"))
cfg = c.read_settings()
check("setup screen: password stored without the trailing space",
      c.hash_password("mat-khau-moi-1", cfg["auth"]["salt"])[0] == cfg["auth"]["password_hash"])

cl2 = TestClient(main.app)
r = cl2.post("/auth/login", data={"username": "phong", "password": "mat-khau-moi-1"})
check(f"login: lower-case username + clean password ({r.status_code})",
      r.status_code == 200 and r.json().get("ok"))
check("login: session cookie set", bool(r.cookies.get("javis_session") or cl2.cookies.get("javis_session")))
check("login: /auth/status then says signed in", cl2.get("/auth/status").json().get("authed") is True)

main._LOGIN_FAILS.clear()
r = TestClient(main.app).post("/auth/login", data={"username": "Phong", "password": "mat-khau-sai-1"})
check(f"login: wrong password still 401 ({r.status_code})", r.status_code == 401)
check("login: an account made on the setup screen gets no env hint (noise on a home PC)",
      "JAVIS_ADMIN_USER" not in (r.json().get("error") or ""))
main._LOGIN_FAILS.clear()
cfg = c.read_settings()
cfg["auth"]["env_applied"] = {"username": "admin", "salt": "s", "hash": "h"}
c.write_settings(cfg)
r = TestClient(main.app).post("/auth/login", data={"username": "Phong", "password": "mat-khau-sai-1"})
check("login: an env-provisioned account's error names JAVIS_ADMIN_USER (reset renames to admin)",
      r.status_code == 401 and "JAVIS_ADMIN_USER" in (r.json().get("error") or ""))
cfg["auth"].pop("env_applied")
c.write_settings(cfg)
main._LOGIN_FAILS.clear()

r = cl2.post("/auth/password", data={"current_password": "mat-khau-moi-1 ",
                                     "password": "  doi-lan-hai-2  "})
check(f"password change: accepted ({r.status_code})", r.status_code == 200 and r.json().get("ok"))
cfg = c.read_settings()
check("password change: stored without surrounding spaces",
      c.hash_password("doi-lan-hai-2", cfg["auth"]["salt"])[0] == cfg["auth"]["password_hash"])

cfg = c.read_settings()
cfg.pop("auth", None)
c.write_settings(cfg)
r = TestClient(main.app).post("/auth/setup", data={"username": "x", "password": "        "})
check(f"setup: an all-space password is refused ({r.status_code})", r.status_code == 400)
check("setup: and nothing was stored", not c.auth_enabled())

if _fails:
    raise SystemExit(f"\nFAIL - test_login_forgiving: {len(_fails)}")
print("\nOK - test_login_forgiving")
