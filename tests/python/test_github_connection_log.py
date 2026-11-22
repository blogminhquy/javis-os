"""Who connected, swapped or disconnected GitHub, and from where (owner, 2026-11-22).

    python tests/run.py github_connection_log      (no network: a local fake GitHub)

Owner incident 2026-11-22: after a stranger took over the Javis account, the owner found GitHub signed out and nothing
said who did it. Every connect, change of account and disconnect now writes one line in the security log with the
Javis account, the real IP and the device, and alerts the owner. A token renewal is not a change and stays silent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-gh-log-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import config  # noqa: E402
import github_repos  # noqa: E402
import security_log  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if (extra is not None and not cond) else ""))
    if not cond:
        _fails.append(name)


def gh_events():
    return [e for e in security_log.recent(200) if str(e.get("event", "")).startswith("github_")]


def latest():
    evs = gh_events()
    return evs[0] if evs else {}


h, s = config.hash_password("owner-password-123")
config.update_settings({"auth": {"username": "owner1", "password_hash": h, "salt": s}})
check("the isolated state is used", str(config.STATE_DIR) == _STATE)

for ev in ("github_connected", "github_changed", "github_disconnected"):
    check(f"{ev} is a security event that alerts the owner", security_log.EVENTS.get(ev) == "alert")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import routes.github as gh_routes  # noqa: E402

app = FastAPI()


@app.middleware("http")
async def _as_api_token(request: Request, call_next):
    # What main._token_ok does for a caller with a Bearer token.
    if request.headers.get("x-test-token-id"):
        request.state.api_token_id = request.headers["x-test-token-id"]
    return await call_next(request)


gh_routes.register(app, gh_routes.GitHubDeps(brain_root=lambda b: b))


class _FromPublicAddress:
    """The request comes straight from a public address (TestClient names its peer "testclient")."""

    def __init__(self, inner, host):
        self.inner, self.host = inner, host

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            scope = {**scope, "client": (self.host, 50123)}
        await self.inner(scope, receive, send)


UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1"
c = TestClient(_FromPublicAddress(app, "203.0.113.9"), headers={"user-agent": UA})
security_log.drain_alerts()

# ---- 1. Connect ----
r = c.post("/github/connect", data={"token": GOOD_TOKEN}).json()
check("connecting through the route works", r.get("ok") and r.get("connected"), r)
evs = gh_events()
check("connecting writes one security line", [e["event"] for e in evs] == ["github_connected"], evs)
e = evs[0] if evs else {}
check("... with the real IP", e.get("ip") == "203.0.113.9", e)
check("... with the device", e.get("ua") == UA, e)
check("... with the Javis account", e.get("user") == "owner1", e)
check("... naming the GitHub login and how it signed in", "@tester" in e.get("detail", ""), e)
check("the owner is alerted", "github_connected" in [a["event"] for a in security_log.drain_alerts()])

# ---- 2. The same account again: no change, no line ----
c.post("/github/connect", data={"token": GOOD_TOKEN})
check("connecting the same account again writes nothing", len(gh_events()) == 1, gh_events())

# ---- 3. Another account replaces it ----
fake.login = "stranger"
r = c.post("/github/connect", data={"token": GOOD_TOKEN}, headers={"x-test-token-id": "tok9"}).json()
check("a different account connects", r.get("login") == "stranger", r)
e = latest()
check("a different account is recorded as a change", e.get("event") == "github_changed", e)
check("... naming the new account and the one it replaced",
      "@stranger" in e.get("detail", "") and "@tester" in e.get("detail", ""), e)
check("... and the API token that did it", e.get("user") == "api token tok9", e)

# ---- 4. Disconnect ----
r = c.post("/github/disconnect").json()
check("disconnecting works", r.get("ok") and r.get("connected") is False, r)
e = latest()
check("disconnecting is recorded", e.get("event") == "github_disconnected", e)
check("... naming the account that was signed out", "@stranger" in e.get("detail", ""), e)
check("... with the real IP and device", e.get("ip") == "203.0.113.9" and e.get("ua") == UA, e)
check("... and the Javis account", e.get("user") == "owner1", e)
alerts = [a["event"] for a in security_log.drain_alerts()]
check("the owner is alerted of the change and the disconnect",
      "github_changed" in alerts and "github_disconnected" in alerts, alerts)
n = len(gh_events())
c.post("/github/disconnect")
check("disconnecting when nothing is connected writes nothing", len(gh_events()) == n)

# ---- 5. Reusing the brain-backup token, from the Python side ----
fake.login = "tester"
config.update_settings({"backup": {"token": GOOD_TOKEN}})
c.post("/github/connect", data={"use_backup": "1"})
e = latest()
check("reusing the backup token is recorded", e.get("event") == "github_connected" and "@tester" in e.get("detail", ""), e)
github_repos.disconnect()
e = latest()
check("a disconnect from code without a request is still recorded",
      e.get("event") == "github_disconnected" and e.get("source") == "internal", e)

# ---- 6. No secret in the log ----
raw = ""
for name in (security_log.LOG_NAME, security_log.OLD_NAME):
    p = config.STATE_DIR / name
    if p.exists():
        raw += p.read_text(encoding="utf-8")
check("the token never reaches the security log", GOOD_TOKEN not in raw and raw.strip() != "")

# ---- 7. Labels and notices ----
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
for ev in ("github_connected", "github_changed", "github_disconnected"):
    check(f"{ev} has a label in both languages", f"sec.ev.{ev}" in vi and f"sec.ev.{ev}" in en)
    check(f"{ev} is listed under account changes", f'{ev}: "change"' in js)
    check(f"{ev} has an alert text for the owner", f'"{ev}": (' in main_src)

fake.close()
print(f"\n{'FAILED ' + str(len(_fails)) if _fails else 'all ok'}")
sys.exit(1 if _fails else 0)
