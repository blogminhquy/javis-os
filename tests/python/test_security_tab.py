"""Account security upgrade after the owner incident of 2026-11-09.

    python tests/run.py security_tab      (no network)

A VPS Javis had its username, password and 2FA changed by someone who edited settings.json on the server. The owner
stayed signed in, nothing logged when or from where, and the way back was a Python one-liner in a root terminal.
This file pins what now exists:

1. Security log: sign-ins (ok, wrong password, wrong code), account changes, with IP and device, never a secret.
2. Sign-in from a network never seen before is an alert for the owner.
3. Security tab data (/auth/security): devices signed in, sign out one or all others; browser session only.
4. settings.json account block edited outside Javis: every session ends, the event is logged and alerted.
5. JAVIS_RESET_2FA turns 2FA off once per value.
6. AI engines are refused when a command or a tool call touches a secret file (secret_guard.py).
7. Hostinger compose: port 7777 listens on 127.0.0.1 once DOMAIN_NAME is set.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sec-tab-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_RESET_2FA", None)

from fastapi.testclient import TestClient   # noqa: E402
import config as c          # noqa: E402
import main                 # noqa: E402
import security_log         # noqa: E402
import secret_guard         # noqa: E402
import coding_terminal      # noqa: E402
import totp                 # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        _fails.append(name)


def set_account(pw="matkhau123", user="owner"):
    cfg = c.read_settings()
    cfg["auth"] = {"username": user, **dict(zip(("password_hash", "salt"), c.hash_password(pw)))}
    c.write_settings(cfg)


def client(ip="203.0.113.10", ua="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"):
    # Peer 127.0.0.1 + X-Forwarded-For: a request coming through Caddy on the same machine.
    cl = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))
    cl.headers.update({"x-forwarded-for": ip, "user-agent": ua})
    return cl


def events(name=None):
    return [e for e in security_log.recent(500) if name is None or e.get("event") == name]


set_account()

# ============================================================
# 1. Security log of sign-ins
# ============================================================
a = client()
r = a.post("/auth/login", data={"username": "owner", "password": "sai-mat-khau"})
check("wrong password refused", r.status_code == 401)
f = events("login_fail")
check("wrong password is logged with the visitor IP (behind a local proxy) and device",
      f and f[0].get("ip") == "203.0.113.10" and "Chrome" in f[0].get("ua", ""), f[:1])
check("the log never holds the typed password", "sai-mat-khau" not in json.dumps(security_log.recent(500)))
r = a.post("/auth/login", data={"username": "owner", "password": "matkhau123"})
check("right password signs in", r.status_code == 200 and r.json().get("ok"))
ok = events("login_ok")
check("successful sign-in is logged", ok and ok[0].get("user") == "owner")
check("first sign-in of the machine is not a new-network alert", not events("login_new_network"))
check("security log file sits in the state folder (survives updates)",
      (c.STATE_DIR / "security_log.jsonl").is_file())

# ============================================================
# 2. New network = alert
# ============================================================
security_log.drain_alerts()
b = client(ip="198.51.100.77", ua="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1")
r = b.post("/auth/login", data={"username": "owner", "password": "matkhau123"})
check("second device signs in", r.status_code == 200)
nn = events("login_new_network")
check("sign-in from another /24 network is flagged", nn and nn[0].get("ip") == "198.51.100.77")
al = security_log.drain_alerts()
check("and queued as an alert for the owner", any(x.get("event") == "login_new_network" for x in al))
txt = main._security_alert_text(nn[0])
check("alert text says what, where and what to do", "198.51.100.77" in txt and "iPhone" in txt)
c2 = client(ip="203.0.113.99")
c2.post("/auth/login", data={"username": "owner", "password": "matkhau123"})
check("same /24 as a known network is not news", len(events("login_new_network")) == 1)

# ============================================================
# 3. /auth/security: devices and history
# ============================================================
d = a.get("/auth/security").json()
check("security tab answers for a browser session", d.get("ok") is True, d)
check("lists the devices signed in", len(d.get("sessions") or []) == 3, len(d.get("sessions") or []))
cur = [x for x in d["sessions"] if x.get("current")]
check("marks the device asking as current", len(cur) == 1 and cur[0].get("ip") == "203.0.113.10")
check("never exposes a raw session token",
      all(len(x["id"]) == 16 for x in d["sessions"]) and not any(t in json.dumps(d) for t in c.SESSIONS))
check("history carries the failed and ok sign-ins",
      {"login_fail", "login_ok", "login_new_network"} <= {e.get("event") for e in d.get("events") or []})
check("failed sign-ins of the last 7 days are counted", d.get("fails_7d") == 1, d.get("fails_7d"))

anon = client()
check("security tab refused without a session", anon.get("/auth/security").status_code in (401, 403))
tok = c.create_api_token("ci", "full")["token"]
r = anon.get("/auth/security", headers={"authorization": f"Bearer {tok}"})
check("security tab refused to an API token (session only)", r.status_code == 403, r.status_code)

phone = [x for x in d["sessions"] if "iPhone" in x.get("ua", "")][0]
r = a.post("/auth/sessions/revoke", data={"id": phone["id"]})
check("one device can be signed out", r.json().get("ok") is True)
check("that device is out", b.get("/auth/security").status_code in (401, 403))
r = a.post("/auth/sessions/revoke", data={"id": cur[0]["id"]})
check("the current device is not ended through the list", r.status_code == 400)
r = a.post("/auth/sessions/revoke", data={"others": "1"})
check("sign out all other devices", r.json().get("ok") is True and r.json().get("ended") == 1, r.json())
check("other device signed out", c2.get("/auth/security").status_code in (401, 403))
check("this device still in", a.get("/auth/security").status_code == 200)
check("sign-out of devices is logged", events("sessions_revoked"))

# Account changes are logged and alerted.
security_log.drain_alerts()
r = a.post("/auth/password", data={"current_password": "matkhau123", "username": "owner2"})
check("username change works", r.json().get("ok") is True)
check("username change logged with the old name",
      events("username_changed") and "owner" in events("username_changed")[0].get("detail", ""))
check("username change is an alert", any(x["event"] == "username_changed" for x in security_log.drain_alerts()))

# ============================================================
# 4. settings.json edited outside Javis
# ============================================================
check("a stamp of the account block exists", (c.STATE_DIR / ".auth_stamp.json").is_file())
check("nothing reported while the file matches", c.auth_guard_check(grace=0) is None)
check("this device is signed in before the outside edit", a.get("/auth/security").status_code == 200)
raw = json.loads(c.SETTINGS_PATH.read_text(encoding="utf-8"))
raw["auth"]["username"] = "VRGROUP"
raw["auth"]["password_hash"], raw["auth"]["salt"] = c.hash_password("ke-la-mat")
time.sleep(0.01)
c.SETTINGS_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
security_log.drain_alerts()
res = c.auth_guard_check(grace=0)
check("outside edit is detected and says what changed",
      res and set(res["changed"]) == {"username", "password"}, res)
check("every session ended", len(c.SESSIONS) == 0)
check("the owner's browser is signed out", a.get("/auth/security").status_code in (401, 403))
check("logged as auth_changed_outside", events("auth_changed_outside"))
check("and alerted", any(x["event"] == "auth_changed_outside" for x in security_log.drain_alerts()))
check("reported once, not on every request", c.auth_guard_check(grace=0) is None)
# The same edit with the grace period: one quick look is not enough, the mismatch must last.
raw["auth"]["username"] = "someone-else"
time.sleep(0.01)
c.SETTINGS_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
check("grace: first sight of a mismatch waits", c.auth_guard_check(grace=0.2) is None)
time.sleep(0.25)
check("grace: still mismatched later -> reported", c.auth_guard_check(grace=0.2) is not None)
# Changes through Javis are never "outside".
set_account(pw="matkhau-moi-1", user="owner")
check("a write through Javis is not an outside edit", c.auth_guard_check(grace=0) is None)

# ============================================================
# 5. JAVIS_RESET_2FA
# ============================================================
c.totp_set(secret=totp.sinh_secret(), enabled=True, recovery=["aaaa-bbbb"], last_step=0)
check("2FA on before the reset", c.totp_enabled())
c.new_session()
os.environ["JAVIS_RESET_2FA"] = "1"
check("JAVIS_RESET_2FA turns 2FA off", c.reset_2fa_from_env() == "reset" and not c.totp_enabled())
check("and ends every session", len(c.SESSIONS) == 0)
check("account itself is kept", c.verify_password("matkhau-moi-1") and c.read_settings()["auth"]["username"] == "owner")
c.totp_set(secret=totp.sinh_secret(), enabled=True, recovery=["cccc-dddd"], last_step=0)
check("same value left in the environment does NOT wipe the new 2FA", c.reset_2fa_from_env() == "" and c.totp_enabled())
os.environ["JAVIS_RESET_2FA"] = "2026-11-09"
check("a new value applies again", c.reset_2fa_from_env() == "reset" and not c.totp_enabled())
os.environ["JAVIS_RESET_2FA"] = "0"
check("'0' does nothing", c.reset_2fa_from_env() == "")
os.environ.pop("JAVIS_RESET_2FA", None)
check("the reset never counts as an outside edit", c.auth_guard_check(grace=0) is None)

# ============================================================
# 6. Secret files are off limits to AI engines
# ============================================================
st = str(c.STATE_DIR)
for cmd in (f"cat {st}/settings.json", f"cd {st} && sed -i 's/a/b/' settings.json",
            "python3 -c \"print(open('/data/state/.secret_key').read())\"", "cat /data/state/se\"tt\"ings.json",
            "cat ~/.codex/auth.json", "cat ~/.claude/.credentials.json", "echo k >> /root/.ssh/authorized_keys",
            "grep token $JAVIS_STATE_DIR/settings.json", f"cp {st}/.sessions.json /tmp/x"):
    check(f"guard refuses: {cmd[:50]}", secret_guard.check_text(cmd) != "")
for cmd in ("cat .vscode/settings.json", "npm test", "ls /data/state", "git status", "python -m pytest tests/"):
    check(f"guard lets through: {cmd}", secret_guard.check_text(cmd) == "")
check("Claude Read of settings.json in the state dir refused",
      secret_guard.check_tool("Read", {"file_path": f"{st}/settings.json"}) == "settings.json")
check("Claude Grep with the state dir as path refused",
      secret_guard.check_tool("Grep", {"path": st, "pattern": "settings"}) != "")
check("Claude Edit of a note in the brain allowed", secret_guard.check_tool("Edit", {"file_path": "/brains/x/a.md"}) == "")
wd = tempfile.mkdtemp(prefix="javis-sec-term-")
out = coding_terminal.chay(f"cat {st}/settings.json", "sec-test", [wd])
check("javis_terminal refuses it at every level", out.startswith("ERROR") and "file bí mật" in out, out[:120])
check("javis_terminal refusal is in the security log", events("agent_secret_blocked"))
out = coding_terminal.chay("echo hello", "sec-test", [wd])
check("javis_terminal still runs ordinary commands", "hello" in out, out[:120])

import asyncio  # noqa: E402
import claude_cli  # noqa: E402
import claude_secret_hook  # noqa: E402
import claude_sdk_engine  # noqa: E402
claude_secret_hook.install()
check("hook installed on ClaudeSDK._options without editing the pinned claude_sdk_engine.py",
      getattr(claude_sdk_engine.ClaudeSDK._options, "_javis_secret_hook", False))
opts = claude_sdk_engine.ClaudeSDK(system_prompt="x", cwd=wd, tag="chat:t")._options()
pre = (getattr(opts, "hooks", None) or {}).get("PreToolUse") or []
check("every Claude turn carries the secret-guard PreToolUse hook",
      any(claude_secret_hook.secret_guard_hook in (m.hooks or []) for m in pre))
check("installing twice does not stack the wrapper",
      claude_secret_hook.install() and not getattr(getattr(claude_sdk_engine.ClaudeSDK._options, "__wrapped__", None),
                                                   "_javis_secret_hook", False))
deny = asyncio.run(claude_secret_hook.secret_guard_hook(
    {"tool_name": "Bash", "tool_input": {"command": f"cat {st}/settings.json"}}, "t1", None))
check("hook denies Bash on settings.json",
      deny.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")
allow = asyncio.run(claude_secret_hook.secret_guard_hook(
    {"tool_name": "Bash", "tool_input": {"command": "ls"}}, "t2", None))
check("hook lets ordinary calls through", allow == {})
check("claude_cli installs the hook where it builds every Claude engine",
      "claude_secret_hook.install()" in (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8"))

# ============================================================
# 7. Hostinger compose: 7777 only on 127.0.0.1 once a domain serves HTTPS
# ============================================================
yml = (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
check("Hostinger compose binds 7777 to 127.0.0.1 when DOMAIN_NAME is set",
      '"${DOMAIN_NAME:+127.0.0.1:}${JAVIS_HOST_PORT:-7777}:7777"' in yml)

# ============================================================
# 8. Dashboard: Security tab with devices and history
# ============================================================
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("Account page has a Security tab", 'data-ac-tab="security"' in js and "renderSecurity" in js)
css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
check("Account page hides the page header so its tabs sit at the top (owner, 2026-11-09)",
      'cv.classList.toggle("cview-tk", id === "account" || id === "webhooks")' in js
      and ".cview.cview-tk .cview-head { display: none; }" in css)
check("Security tab reads /auth/security and can sign out other devices",
      'fetch("/auth/security")' in js and "/auth/sessions/revoke" in js)
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
missing = [f"sec.ev.{e}" for e in security_log.EVENTS if f"sec.ev.{e}" not in vi or f"sec.ev.{e}" not in en]
check("every security event has a label in vi.json and en.json", not missing, missing)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
