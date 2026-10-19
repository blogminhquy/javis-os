"""Turning off login must not cost the owner their 2FA, nor open the machine (security report C2).

    python tests/run.py auth_disable      (no network)

Before 0.224.0, POST /auth/disable took no password, accepted an API token and replaced the whole
`auth` block, 2FA included. One click on a borrowed session turned 2FA off for good, and on a
machine behind a tunnel it left the dashboard (and its Terminal) open to the Internet. This file
pins the new contract:

1. browser session only, current password, and a 2FA code when 2FA is on;
2. refused on a public bind and on a request that arrives through a tunnel or proxy;
3. the 2FA config survives, and is back in force once a password is set again.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-auth-disable-test-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)

from fastapi.testclient import TestClient   # noqa: E402
import config as c   # noqa: E402
import main          # noqa: E402
import totp          # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# The browser on the machine itself: loopback address, no forwarding header.
cl = TestClient(main.app, client=("127.0.0.1", 50000), base_url="http://localhost:7777")
PW = "matkhau123"
SEC = totp.sinh_secret()
REC = totp.sinh_ma_khoi_phuc()


def next_code():
    """A code the server accepts right now: rewind the used-step mark, then give the current step.
    Codes are single use, so a test that signs in more than once per 30 s needs this."""
    b = totp.buoc_hien_tai()
    c.totp_set(secret=None, last_step=b - 2)
    return totp.ma_cua_buoc(SEC, b)


def set_account_with_2fa():
    cfg = c.read_settings()
    cfg["auth"] = {"username": "admin",
                   **dict(zip(("password_hash", "salt"), c.hash_password(PW)))}
    c.write_settings(cfg)
    c.totp_set(secret=SEC, enabled=True, recovery=REC, last_step=0)
    main._LOGIN_FAILS.clear()
    cl.cookies.clear()
    r = cl.post("/auth/login", data={"username": "admin", "password": PW, "code": next_code()})
    assert r.json().get("ok"), r.text


def disable(**data):
    return cl.post("/auth/disable", data=data, headers=data.pop("_headers", None) or {})


# ============================================================
# 1. What it asks for
# ============================================================
set_account_with_2fa()
r = disable()
check("no password -> 401", r.status_code == 401)
r = disable(password="sai")
check("wrong password -> 401, and does not reveal needs_2fa",
      r.status_code == 401 and r.json().get("needs_2fa") is None)
r = disable(password=PW)
check("right password, no code -> 401 needs_2fa (the dashboard then asks for the code)",
      r.status_code == 401 and r.json().get("needs_2fa") is True)
r = disable(password=PW, code="000000")
check("wrong code -> 401", r.status_code == 401)
check("login is still on after the refused attempts", c.auth_enabled() and c.totp_enabled())

# An API token never turns login off, even a full one.
tok = c.create_api_token("t", "full")["token"]
_cookies = dict(cl.cookies)
cl.cookies.clear()
r = cl.post("/auth/disable", data={"password": PW, "code": next_code()},
            headers={"Authorization": f"Bearer {tok}"})
check("API token -> 403 (browser session only)", r.status_code == 403 and c.auth_enabled())
for k, v in _cookies.items():
    cl.cookies.set(k, v)

# ============================================================
# 2. Never on a machine reachable from outside
# ============================================================
r = cl.post("/auth/disable", data={"password": PW, "code": next_code()},
            headers={"X-Forwarded-For": "203.0.113.9"})
check("through a proxy/tunnel (forwarding header) -> 403", r.status_code == 403 and c.auth_enabled())
r = cl.post("/auth/disable", data={"password": PW, "code": next_code()},
            headers={"CF-Connecting-IP": "203.0.113.9"})
check("through a cloudflared tunnel -> 403", r.status_code == 403 and c.auth_enabled())
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
r = disable(password=PW, code=next_code())
check("public server (require_login) -> 403", r.status_code == 403 and c.auth_enabled())
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
lan = TestClient(main.app, client=("192.168.1.20", 50000), base_url="http://localhost:7777")
for k, v in dict(cl.cookies).items():
    lan.cookies.set(k, v)
r = lan.post("/auth/disable", data={"password": PW, "code": next_code()})
check("from another device on the LAN -> 403", r.status_code == 403 and c.auth_enabled())

# ============================================================
# 3. The real thing, and 2FA survives it
# ============================================================
r = disable(password=PW, code=next_code())
check("password + code on the machine itself -> ok", r.json().get("ok") is True)
cfg = c.read_settings()
check("login is off (no password left)", not c.auth_enabled(cfg))
check("CANARY: 2FA config is KEPT (enabled + same secret)",
      c.totp_enabled(cfg) and c.totp_secret(cfg) == SEC)
check("old sessions are dropped", not c.valid_session(dict(cl.cookies).get("javis_session", "")))

# Setting a password again brings 2FA back in force.
r = cl.post("/auth/setup", data={"username": "admin", "password": PW})
check("setup again -> ok", r.json().get("ok") is True)
check("CANARY: 2FA is still on after setup", c.totp_enabled() and c.totp_secret() == SEC)
cl.cookies.clear()
r = cl.post("/auth/login", data={"username": "admin", "password": PW})
check("and the login page asks for the code again",
      r.status_code == 401 and r.json().get("needs_2fa") is True)

# A recovery code also works, and is spent.
r = cl.post("/auth/login", data={"username": "admin", "password": PW, "code": next_code()})
check("sign in again with a code", r.json().get("ok") is True)
r = disable(password=PW, code=REC[0])
check("recovery code accepted to turn login off", r.json().get("ok") is True)
check("and that recovery code is spent", c.totp_recovery_left() == len(REC) - 1)

# JAVIS_ADMIN_PASSWORD creating the account at boot must not drop the kept 2FA either.
os.environ["JAVIS_ADMIN_PASSWORD"] = "envpass123"
check("env admin is created", c.provision_admin_from_env() == "created")
check("CANARY: 2FA kept when the env creates the account", c.totp_enabled() and c.totp_secret() == SEC)
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)

# Turning 2FA off for real still works and still wipes it.
c.totp_tat()
check("totp_tat still turns 2FA off", not c.totp_enabled() and c.kept_totp() == {})

# ============================================================
# 4. Source canaries
# ============================================================
_src = (SERVER / "main.py").read_text(encoding="utf-8")
_blk = _src[_src.index('@app.post("/auth/disable")'):]
_blk = _blk[:_blk.index("\n@app.")]
check("CANARY: /auth/disable asks for a browser session", "_doi_phien_that(request)" in _blk)
check("CANARY: /auth/disable no longer builds a fresh auth object",
      'cfg["auth"] = {"username": ""' not in _blk)
check("CANARY: /auth/disable is not public", '"/auth/disable"' not in
      _src[_src.index("_AUTH_PUBLIC_EXACT = "):_src.index("_AUTH_PUBLIC_EXACT = ") + 400])

print()
if _fails:
    print(f"{len(_fails)} test FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All auth_disable tests passed.")
