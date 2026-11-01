"""Sign in to GitHub with one button: the device flow of the Javis OS GitHub App (0.430.0).

    python tests/run.py github_oauth      (no network: a local fake GitHub serves both github.com and the API)

Covered:
  1. Start asks GitHub for a code with the Javis app's client id and returns what the card shows.
  2. Polls respect GitHub's interval (an early poll never reaches GitHub), `slow_down` lengthens it.
  3. An approved sign-in stores the token encrypted, as source "app"; status never returns it and reports installs.
  4. Cancel on GitHub, an expired code and a poll with nothing started each end with a plain reason.
  5. An expiring token is renewed with its refresh token; a refused renewal reads as signed out.
  6. The poll route stores the token server side and never sends it to the browser.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-gh-oauth-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN  # noqa: E402

fake = FakeGitHub(scopes=None)          # GitHub App tokens carry no X-OAuth-Scopes header
os.environ["JAVIS_GITHUB_API"] = fake.url
os.environ["JAVIS_GITHUB_WEB"] = fake.url

import config  # noqa: E402
import github_oauth  # noqa: E402
import github_repos  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def due():
    """Skip the wait between polls, as if the interval had passed."""
    github_oauth._pending["next_at"] = 0


def reset_device(**kw):
    fake.device.update({"pending": 1, "slow": False, "deny": False, "expires_in": 0, "refresh_token": "",
                        "refreshed_token": "", "polls": 0, **kw})
    fake.device["client_ids"].clear()


# ---- 1. Start ----
check("the app's client id is the registered one", github_oauth.client_id() == "Iv23limeL0BsyXptmTz2")
check("repos are picked on the Javis OS app page",
      github_oauth.install_url() == "https://github.com/apps/javis-os/installations/new")
reset_device(pending=2, slow=True)
d = github_oauth.start()
check("start returns the code to type", d["user_code"] == "ABCD-1234")
check("start returns the page to type it on", d["verification_uri"] == "https://github.com/login/device")
check("start sends the app's client id", fake.device["client_ids"] == ["Iv23limeL0BsyXptmTz2"])
check("the device code stays in the server", "dev-123" not in json.dumps(d))

# ---- 2. Interval ----
check("a poll before the interval is pending", github_oauth.poll()["status"] == "pending")
check("... and never reaches GitHub", fake.device["polls"] == 0)
due()
check("slow_down reads as pending", github_oauth.poll()["status"] == "pending")
check("slow_down lengthens the interval", github_oauth._pending["interval"] == 2)
check("the next poll waits for it", github_oauth._pending["next_at"] > time.time() + 1)
due()
check("authorization_pending reads as pending", github_oauth.poll()["status"] == "pending")

# ---- 3. Approved ----
due()
out = github_oauth.poll()
check("an approved sign-in hands the token over", out["status"] == "done" and out["token"]["access_token"] == GOOD_TOKEN)
check("a finished sign-in leaves nothing pending", github_oauth.pending() is False)
st = github_repos.connect_app(out["token"])
check("the connection is stored as signed in with the app", st["connected"] and st["source"] == "app")
check("the login is shown", st["login"] == "tester")
check("an app token is not flagged for missing scopes", st["missing"] == [])
check("status says the app is installed somewhere", st["installs"] == 1)
check("status carries the install link", "javis-os" in st["install_url"])
check("status never returns the token", GOOD_TOKEN not in json.dumps(st))
raw = json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8"))
check("the token is not stored in clear", GOOD_TOKEN not in json.dumps(raw))
check("Javis uses the app token for GitHub", github_repos.token() == GOOD_TOKEN)
fake.installs = 0
github_repos._INSTALL_CACHE.update(at=0.0, n=-1)
check("signed in with no repo picked says so", github_repos.status()["installs"] == 0)
fake.installs = 1
github_repos.disconnect()
check("disconnect forgets the app token", github_repos.status()["connected"] is False and github_repos.token() == "")

# ---- 4. Failures ----
reset_device(pending=0, deny=True)
github_oauth.start()
due()
out = github_oauth.poll()
check("Cancel on GitHub ends the sign-in with a reason", out["status"] == "error" and out["error"])
check("... and clears it", github_oauth.pending() is False)
check("a poll with nothing started is an error", github_oauth.poll()["status"] == "error")
reset_device()
github_oauth.start()
github_oauth._pending["expires_at"] = time.time() - 1
check("an expired code is an error", github_oauth.poll()["status"] == "error")
reset_device()
github_oauth.start()
github_oauth.cancel()
check("cancel drops the pending sign-in", github_oauth.pending() is False)

# ---- 5. Expiring tokens ----
reset_device(pending=0, expires_in=28800, refresh_token="ghr_first", refreshed_token="ghu_renewed")
github_oauth.start()
due()
out = github_oauth.poll()
check("an expiring token keeps its expiry", out["token"]["expires_at"] > time.time())
github_repos.connect_app(out["token"])
raw = json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8"))
check("the refresh token is not stored in clear", "ghr_first" not in json.dumps(raw))
check("a fresh token is used as is", github_repos.token() == GOOD_TOKEN)
config.update_settings({"github": {"expires_at": time.time() - 5}})
check("an expired token is renewed", github_repos.token() == "ghu_renewed")
conn = github_repos._read_conn()
check("the renewed token and its new refresh token are kept",
      conn["token"] == "ghu_renewed" and conn["refresh_token"] == "ghr_next")
config.update_settings({"github": {"expires_at": time.time() - 5}})
fake.device["refreshed_token"] = ""
check("a refused renewal reads as signed out", github_repos.token() == "" and github_repos.status()["connected"] is False)
github_repos.disconnect()

# ---- 6. Route ----
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.github as gh_routes
except Exception as e:  # pragma: no cover
    print(f"skip route checks: {type(e).__name__}: {e}")
else:
    app = FastAPI()
    gh_routes.register(app, gh_routes.GitHubDeps(brain_root=lambda b: b))
    c = TestClient(app)
    reset_device(pending=1)
    r = c.post("/github/oauth/start").json()
    check("the start route returns the code", r["ok"] and r["user_code"] == "ABCD-1234")
    due()
    r = c.post("/github/oauth/poll").json()
    check("the poll route says pending", r["ok"] and r["status"] == "pending")
    due()
    r = c.post("/github/oauth/poll").json()
    check("the poll route connects", r["ok"] and r["status"] == "connected" and r["source"] == "app")
    check("the poll route never sends the token to the browser", GOOD_TOKEN not in json.dumps(r))
    r = c.post("/github/oauth/poll").json()
    check("polling again after success is a plain error", r["ok"] is False and r["error"])
    check("cancel route answers", c.post("/github/oauth/cancel").json()["ok"] is True)

fake.close()
print(f"\n{'FAILED ' + str(len(_fails)) if _fails else 'all ok'}")
sys.exit(1 if _fails else 0)
