"""A lost password must never reopen the public account form to a stranger, and the log must name the real visitor.

    python tests/run.py setup_after_account_lost      (no network)

Owner incident 2026-11-22 (the second one, the first was 2026-11-12): the owner's password vanished from settings.json
on a VPS behind Cloudflare. With no password, POST /auth/setup is open to anyone, and a stranger's iPhone created the
account "trolytina" from the login page. The security log named only a Cloudflare edge address (172.71.219.14), not
the visitor. Both times, tests had been run inside the live container right before, and the test runner passed the
container's own JAVIS_STATE_DIR (the real settings) and JAVIS_ADMIN_* to every test.

Pinned here:
1. tests never inherit the live state folder or the deploy variables (tests/python/_live_env.py, _paths, run.py);
2. write_settings refuses to drop the owner's password unless the caller says so (only POST /auth/disable does);
3. once an owner account has existed, the account form only opens on the machine itself, or after the reset tool;
   with JAVIS_ADMIN_PASSWORD set the account is simply restored from it, 2FA kept;
4. the security log and the sign-in lockout use the visitor's address, read through Cloudflare and local proxies,
   and an address a visitor typed into a header is never believed.
"""
from _paths import ROOT, SERVER, TEST_TMP  # noqa: E402,F401
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-setup-lost-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"      # a VPS: the dashboard is reachable from the Internet
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

from fastapi.testclient import TestClient   # noqa: E402
import config as c          # noqa: E402
import main                 # noqa: E402
import security_log         # noqa: E402

STATE = Path(os.environ["JAVIS_STATE_DIR"])
_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)[:300]))
    if not cond:
        _fails.append(name)


def events(name):
    return [e for e in security_log.recent(500) if e.get("event") == name]


# A visitor through Cloudflare and the reverse proxy of the VPS (Traefik in Docker): the proxy connects from the
# Docker network and appends the Cloudflare edge it got the request from.
EDGE = "172.71.219.14"


def via_cloudflare(visitor, edge=EDGE):
    return {"X-Forwarded-For": f"{visitor}, {edge}", "CF-Connecting-IP": visitor, "X-Real-IP": edge}


remote = TestClient(main.app, client=("172.18.0.5", 41000), base_url="https://javis.example.com")
here = TestClient(main.app, client=("127.0.0.1", 50000), base_url="http://localhost:7777")
PW = "chu-may-123"


def wipe_from_outside():
    """What the incident left: username, password and salt emptied in the file itself, 2FA kept."""
    raw = json.loads(c.SETTINGS_PATH.read_text(encoding="utf-8"))
    a = raw.get("auth") or {}
    a.update(username="", password_hash="", salt="")
    a.pop("env_applied", None)
    raw["auth"] = a
    c.SETTINGS_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    c._SETTINGS_SIG.drop()     # a hand edit shows after about a second; the test does not wait for it


def status():
    return remote.get("/auth/status").json()


# ============================================================
# 1. Tests do not inherit the live machine
# ============================================================
sys.path.insert(0, str(ROOT / "tests" / "python"))
import _live_env  # noqa: E402

live = {"JAVIS_STATE_DIR": "/data/state", "BRAINS_DIR": "/brains", "BRAIN_PATH": "/data/brain",
        "OBSIDIAN_VAULT_PATH": "/data/vault", "JAVIS_ADMIN_PASSWORD": "not-a-real-one", "JAVIS_ADMIN_USER": "owner",
        "JAVIS_HOST": "0.0.0.0", "JAVIS_PORT": "7777", "JAVIS_DEPLOY_TARGET": "hostinger",
        "DOMAIN_NAME": "javis.example.com", "WATCHTOWER_TOKEN": "not-a-real-one", "PATH": os.environ["PATH"]}
env = _live_env.scrub(dict(live))
check("the live state folder and brains are dropped",
      not any(k in env for k in ("JAVIS_STATE_DIR", "BRAINS_DIR", "BRAIN_PATH", "OBSIDIAN_VAULT_PATH")), env)
check("the deploy variables are dropped (admin password, bind, deploy target, domain, update token)",
      not any(k in env for k in ("JAVIS_ADMIN_PASSWORD", "JAVIS_ADMIN_USER", "JAVIS_HOST", "JAVIS_PORT",
                                 "JAVIS_DEPLOY_TARGET", "DOMAIN_NAME", "WATCHTOWER_TOKEN")), env)
check("PATH is untouched", env.get("PATH") == os.environ["PATH"])
tmp_state = tempfile.mkdtemp(prefix="javis-kept-")
check("a state folder a test made in the temp folder is kept",
      _live_env.scrub({"JAVIS_STATE_DIR": tmp_state}).get("JAVIS_STATE_DIR") == tmp_state)
check("a folder whose name merely starts like the temp folder is not",
      "JAVIS_STATE_DIR" not in _live_env.scrub({"JAVIS_STATE_DIR": str(TEST_TMP) + "-evil"}))

# Importing _paths (every test does it first) scrubs the process, the way the container's env reaches a test.
child_env = {k: v for k, v in os.environ.items() if k not in ("JAVIS_TEST_ENV_SCRUBBED",)}
child_env.update({k: v for k, v in live.items() if k != "PATH"})
child_env.pop("JAVIS_TEST_ENV_SCRUBBED", None)
code = ("import sys; sys.path.insert(0, sys.argv[1]); import _paths, os, json; "
        "print(json.dumps({k: os.environ.get(k) for k in sys.argv[2:]}))")
out = subprocess.run([sys.executable, "-c", code, str(ROOT / "tests" / "python"), *sorted(live)],
                     env=child_env, capture_output=True, text=True, timeout=60)
seen = json.loads((out.stdout or "{}").strip().splitlines()[-1] if out.stdout.strip() else "{}")
check("a test process started inside the live container does not see its state, brains or admin password",
      seen and all(seen.get(k) is None for k in live if k != "PATH"), out.stdout + out.stderr)

# tests/run.py hands every test the same scrubbed environment.
sys.path.insert(0, str(ROOT / "tests"))
import run as test_runner  # noqa: E402

renv = test_runner.child_env(dict(live))
check("tests/run.py gives tests no live state folder and no admin password",
      "JAVIS_STATE_DIR" not in renv and "JAVIS_ADMIN_PASSWORD" not in renv and renv.get("PYTHONIOENCODING") == "utf-8",
      sorted(renv))

# ============================================================
# 2. A fresh install still opens the account form, from anywhere
# ============================================================
st = status()
check("fresh install: needs setup, not locked", st.get("needs_setup") is True and st.get("setup_locked") is False, st)
r = remote.post("/auth/setup", data={"username": "chu", "password": PW}, headers=via_cloudflare("198.51.100.7"))
check("fresh install: the first account is created from a browser through Cloudflare", r.json().get("ok") is True,
      r.text)
ev = events("setup")
check("the setup is logged with the visitor's address, not Cloudflare's", ev and ev[0].get("ip") == "198.51.100.7", ev)

# ============================================================
# 3. The owner's password is never dropped by an ordinary save
# ============================================================
cfg = c.read_settings()
cfg["auth"]["password_hash"] = ""
cfg["auth"]["salt"] = ""
cfg["auth"]["username"] = ""
c.write_settings(cfg)
check("a save without the password keeps the owner's account", c.auth_enabled() and
      c.read_settings()["auth"]["username"] == "chu")
check("and is logged as an alert", events("account_clear_blocked") and
      security_log.level_of("account_clear_blocked") == "alert")
cfg = c.read_settings()
cfg.pop("auth")
c.write_settings(cfg)
check("a save with the whole account block missing keeps it too", c.auth_enabled())
cfg = c.read_settings()
cfg["auth"]["password_hash"] = "ab" * 32
cfg["auth"]["salt"] = "cd" * 16
c.write_settings(cfg)
check("a real password change still goes through", c.read_settings()["auth"]["password_hash"] == "ab" * 32)
h, salt = c.hash_password(PW)
cfg = c.read_settings()
cfg["auth"].update(password_hash=h, salt=salt)
c.write_settings(cfg)

# ============================================================
# 4. The password vanishes from the file: the form stays shut to strangers
# ============================================================
wipe_from_outside()
c.auth_guard_check(grace=0)     # the running Javis notices and adopts the new block
st = status()
check("after the wipe: needs setup AND locked", st.get("needs_setup") is True and st.get("setup_locked") is True, st)
r = remote.post("/auth/setup", data={"username": "trolytina", "password": "stranger-123"},
                headers=via_cloudflare("203.0.113.66"))
check("a stranger through Cloudflare cannot create an account (403)", r.status_code == 403 and not c.auth_enabled(),
      r.text)
check("the refusal says how the owner gets back in", "JAVIS_ADMIN_PASSWORD" in r.json().get("error", ""), r.text)
blocked = events("setup_blocked")
check("the attempt is logged as an alert with the stranger's real address",
      blocked and blocked[0].get("ip") == "203.0.113.66" and blocked[0].get("user") == "trolytina"
      and security_log.level_of("setup_blocked") == "alert", blocked)
r = here.post("/auth/setup", data={"username": "x", "password": "stranger-123"},
              headers={"X-Forwarded-For": "203.0.113.66"})
check("a tunnel on the machine (loopback with a forwarding header) is not 'the machine itself'",
      r.status_code == 403 and not c.auth_enabled(), r.text)
rebind = TestClient(main.app, client=("127.0.0.1", 50001), base_url="http://evil.example")
r = rebind.post("/auth/setup", data={"username": "x", "password": "stranger-123"})
check("a page that rebinds its own name to 127.0.0.1 is not 'the machine itself' either",
      r.status_code == 403 and not c.auth_enabled(), r.text)
lan = TestClient(main.app, client=("192.168.1.20", 50000), base_url="http://192.168.1.10:7777")
r = lan.post("/auth/setup", data={"username": "x", "password": "stranger-123"})
check("another device on the LAN cannot either", r.status_code == 403 and not c.auth_enabled(), r.text)

# The sticky mark survives a stamp written after the wipe, and a stamp from before this version.
check("owner_known after the guard re-stamped the empty block", c.owner_known())
stamp = json.loads((STATE / ".auth_stamp.json").read_text(encoding="utf-8"))
stamp.pop("owner", None)
(STATE / ".auth_stamp.json").write_text(json.dumps(stamp), encoding="utf-8")
check("owner_known from the security log when the stamp has no mark", c.owner_known())

# ============================================================
# 5. JAVIS_ADMIN_PASSWORD brings the account back by itself, 2FA kept
# ============================================================
cfg = c.read_settings()
cfg["auth"]["totp"] = {"enabled": True, "secret": "JBSWY3DPEHPK3PXP", "recovery": [], "last_step": 0}
c.write_settings(cfg)
os.environ["JAVIS_ADMIN_PASSWORD"] = "env-pass-123"
os.environ["JAVIS_ADMIN_USER"] = "chu"
st = status()
check("with the env password set, the status call restores the account", st.get("needs_setup") is False
      and c.auth_enabled(), st)
check("the restored account keeps 2FA", c.totp_enabled())
check("and the restore is logged", any("restored" in (e.get("detail") or "") for e in events("env_account_created")))
r = remote.post("/auth/login", data={"username": "chu", "password": "env-pass-123"},
                headers=via_cloudflare("198.51.100.7"))
check("the owner signs in with the env password (and is asked for the 2FA code)",
      r.status_code == 401 and r.json().get("needs_2fa") is True, r.text)
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_ADMIN_USER", None)

# ============================================================
# 6. On the machine itself, or after the reset tool, the owner can set a new one
# ============================================================
wipe_from_outside()
r = here.post("/auth/setup", data={"username": "chu", "password": PW})
check("the browser on the machine itself can set the account again", r.json().get("ok") is True, r.text)
check("and 2FA kept from before is back in force", c.totp_enabled())

sys.path.insert(0, str(ROOT / "tools"))
import reset_auth  # noqa: E402

env_file = STATE / ".env-none"
rc = reset_auth.main(["--state-dir", str(STATE), "--env-file", str(env_file)])
c._SETTINGS_SIG.drop()     # the tool writes the file itself; a running Javis sees it about a second later
check("reset tool runs", rc == 0)
check("reset tool leaves a reopen mark", (STATE / ".setup_reopen").is_file())
st = status()
check("after the reset tool: needs setup and NOT locked", st.get("needs_setup") is True
      and st.get("setup_locked") is False, st)
r = remote.post("/auth/setup", data={"username": "chu", "password": PW}, headers=via_cloudflare("198.51.100.7"))
check("after the reset tool the owner can set a new password from their phone", r.json().get("ok") is True, r.text)
check("the reopen mark is used up", not (STATE / ".setup_reopen").exists())
wipe_from_outside()
check("a later wipe locks the form again", status().get("setup_locked") is True)
(STATE / ".setup_reopen").write_text(json.dumps({"ts": 1}), encoding="utf-8")
check("an old reopen mark (over a day) does not open it", status().get("setup_locked") is True)
(STATE / ".setup_reopen").unlink()

# POST /auth/disable is the one way to clear the account on purpose, and still works (on the machine itself).
r = here.post("/auth/setup", data={"username": "chu", "password": PW})
assert r.json().get("ok"), r.text
c.totp_tat()
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
r = here.post("/auth/disable", data={"password": PW})
check("turning login off on the machine itself still clears the password", r.json().get("ok") is True
      and not c.auth_enabled(), r.text)
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
check("and that does not count as a blocked clear", not any(
    e.get("ts", 0) > 0 and "disable" in (e.get("detail") or "") for e in events("account_clear_blocked")))
os.environ["JAVIS_ADMIN_PASSWORD"] = "env-pass-123"
st = status()
check("login turned off on purpose: the form is a first one again, and the env password waits for the next boot",
      st.get("needs_setup") is True and st.get("setup_locked") is False and not c.auth_enabled(), st)
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)

# ============================================================
# 7. The real visitor's address
# ============================================================


class Req:
    def __init__(self, peer, headers):
        self.client = type("C", (), {"host": peer})()
        self.headers = {k.lower(): v for k, v in headers.items()}


ip = security_log.client_ip
check("Cloudflare -> proxy on the Docker network: the visitor",
      ip(Req("172.18.0.5", via_cloudflare("198.51.100.7"))) == "198.51.100.7")
check("Cloudflare -> proxy, IPv6 edge: the visitor",
      ip(Req("172.18.0.5", via_cloudflare("2001:db8::7", edge="2400:cb00:2049:1::a29f:1"))) == "2001:db8::7")
check("Cloudflare edge straight to Javis: the visitor",
      ip(Req(EDGE, {"CF-Connecting-IP": "198.51.100.7"})) == "198.51.100.7")
check("cloudflared on the machine: the visitor",
      ip(Req("127.0.0.1", {"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "198.51.100.7"})) == "198.51.100.7")
check("a visitor's own X-Forwarded-For is ignored behind a proxy (the proxy's entry wins)",
      ip(Req("172.18.0.5", {"X-Forwarded-For": "1.2.3.4, 203.0.113.66"})) == "203.0.113.66")
check("a visitor's CF-Connecting-IP is ignored when the hop is not Cloudflare",
      ip(Req("172.18.0.5", {"X-Forwarded-For": "203.0.113.66", "CF-Connecting-IP": "1.2.3.4"})) == "203.0.113.66")
check("a visitor straight from the Internet cannot pick an address",
      ip(Req("203.0.113.66", {"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "1.2.3.4"})) == "203.0.113.66")
check("through Cloudflare a forged X-Forwarded-For before the edge is ignored",
      ip(Req("172.18.0.5", {"X-Forwarded-For": f"1.2.3.4, 198.51.100.7, {EDGE}",
                            "CF-Connecting-IP": "198.51.100.7"})) == "198.51.100.7")
check("a broken CF-Connecting-IP falls back to the edge address",
      ip(Req("172.18.0.5", {"X-Forwarded-For": EDGE, "CF-Connecting-IP": "not-an-ip"})) == EDGE)
check("the browser on the machine itself: loopback", ip(Req("127.0.0.1", {})) == "127.0.0.1")

# The sign-in lockout counts per visitor, not per Cloudflare edge: before, one stranger guessing passwords through an
# edge locked out the owner coming through the same edge (the 2026-11-22 log shows login_locked on an edge address).
r = here.post("/auth/setup", data={"username": "chu", "password": PW})     # login was turned off just above
assert r.json().get("ok"), r.text
main._LOGIN_FAILS.clear()
old_max = main._LOGIN_MAX_FAILS
main._LOGIN_MAX_FAILS = 2
for _ in range(2):
    remote.post("/auth/login", data={"username": "chu", "password": "wrong-pass"},
                headers=via_cloudflare("203.0.113.66"))
r = remote.post("/auth/login", data={"username": "chu", "password": "wrong-pass"},
                headers=via_cloudflare("203.0.113.66"))
check("the stranger is locked out", r.status_code == 429, r.text)
r = remote.post("/auth/login", data={"username": "chu", "password": PW}, headers=via_cloudflare("198.51.100.7"))
check("the owner coming through the same Cloudflare edge is not", r.status_code != 429, r.text)
main._LOGIN_MAX_FAILS = old_max
main._LOGIN_FAILS.clear()

# ============================================================
# 8. The dashboard shows the locked form as a sign-in page with a reason
# ============================================================
app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("the dashboard knows setup_locked", "setup_locked" in app_js and 'app.setup_locked' in app_js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}.json has the locked-setup text", bool(d.get("app.setup_locked")))
    check(f"{lang}.json labels the new security events",
          bool(d.get("sec.ev.setup_blocked")) and bool(d.get("sec.ev.account_clear_blocked")))

print()
if _fails:
    print(f"{len(_fails)} test FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All setup_after_account_lost tests passed.")
