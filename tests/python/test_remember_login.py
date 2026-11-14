"""The "Keep me signed in on this device" box on the sign-in screen.

    python tests/run.py remember_login      (no network)

Owner request 2026-11-14: every sign-in was kept for 30 days, so signing in on someone else's device left Javis open
there until someone signed out by hand. Unticked, the session must end when the browser closes.

Contract:
1. Ticked, or a client that does not send the field: a 30-day cookie, exactly as before.
2. Unticked: a cookie with no Max-Age (the browser drops it on close) and a session the server marks as short.
3. A short session ends after _SHORT_SESSION_IDLE with no request, and _SHORT_SESSION_MAX after sign-in at the latest,
   because browsers that restore their last session keep session cookies. A remembered one is untouched by both.
4. A short session is never renewed, so the sliding renewal can never hand it a 30-day cookie.
5. Changing the password on a short session keeps it short.
6. The flag survives a restart, and a session from before this change counts as remembered.
7. The device list tells the two apart; the sign-in screen has the box, ticked by default, and sends it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-remember-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"

from fastapi.testclient import TestClient   # noqa: E402
import config as c   # noqa: E402
import main          # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


cl = TestClient(main.app)
cfg = c.read_settings()
cfg["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"), c.hash_password("matkhau123")))}
c.write_settings(cfg)


def login(**extra):
    c.clear_sessions()
    cl.cookies.clear()
    r = cl.post("/auth/login", data={"username": "admin", "password": "matkhau123", **extra})
    return r, cl.cookies.get("javis_session", "")


# 1. Ticked / field missing: unchanged 30-day cookie
r, tok = login()
sc = r.headers.get("set-cookie", "").lower()
check("no remember field -> signed in", r.status_code == 200 and c.valid_session(tok))
check("no remember field -> 30-day cookie", "max-age=2592000" in sc)
check("no remember field -> remembered session", c.session_remembered(tok))
r, tok = login(remember="1")
check("remember=1 -> 30-day cookie", "max-age=2592000" in r.headers.get("set-cookie", "").lower())

# 2. Unticked: browser-session cookie, short session on the server
r, tok = login(remember="0")
sc = r.headers.get("set-cookie", "").lower()
check("remember=0 -> signed in", r.status_code == 200 and c.valid_session(tok))
check("remember=0 -> cookie has no max-age", "javis_session=" in sc and "max-age" not in sc)
check("remember=0 -> cookie has no expires", "expires" not in sc)
check("remember=0 -> session marked short", not c.session_remembered(tok))
check("the dashboard works on a short session", cl.get("/auth/status").json().get("authed") is True)

# 3. Idle and absolute limits
r, tok = login(remember="0")
c.SESSION_META[tok]["last"] = time.time() - c._SHORT_SESSION_IDLE - 60
check("short session idle past the limit -> ended", not c.valid_session(tok))
check("and it is gone from the store", tok not in c.SESSIONS)

r, tok = login(remember="0")
c.SESSIONS[tok] = time.time() - c._SHORT_SESSION_MAX - 60
c.SESSION_META[tok]["last"] = time.time()
check("short session past the day cap -> ended even while in use", not c.valid_session(tok))

r, tok = login(remember="0")
c.SESSION_META[tok]["last"] = time.time() - c._SHORT_SESSION_IDLE + 600
check("short session used within the idle limit -> still valid", c.valid_session(tok))

r, tok = login()
c.SESSIONS[tok] = time.time() - 3 * 86400
c.SESSION_META.setdefault(tok, {})["last"] = time.time() - 2 * 86400
check("remembered session idle for days -> still valid", c.valid_session(tok))

# 4. Never renewed
r, tok = login(remember="0")
c.SESSIONS[tok] = time.time() - c._SESSION_RENEW_AFTER - 60
check("short session older than a day is not renewed", not c.renew_session(tok))
check("CANARY: a remembered one of the same age is renewed", (lambda t: (c.SESSIONS.__setitem__(
    t, time.time() - c._SESSION_RENEW_AFTER - 60), c.renew_session(t))[1])(c.new_session()))

# 5. Password change keeps the choice
r, tok = login(remember="0")
r = cl.post("/auth/password", data={"current_password": "matkhau123", "username": "admin", "password": "matkhau123"})
new_tok = cl.cookies.get("javis_session", "")
sc = r.headers.get("set-cookie", "").lower()
check("password change on a short session -> ok", r.status_code == 200 and c.valid_session(new_tok))
check("password change on a short session -> new session still short",
      new_tok != tok and not c.session_remembered(new_tok) and "max-age" not in sc)
r, tok = login()
r = cl.post("/auth/password", data={"current_password": "matkhau123", "username": "admin", "password": "matkhau123"})
check("password change on a remembered session -> stays 30 days",
      "max-age=2592000" in r.headers.get("set-cookie", "").lower()
      and c.session_remembered(cl.cookies.get("javis_session", "")))

# 6. Restart and older sessions
r, tok = login(remember="0")
meta = json.loads((c.STATE_DIR / ".sessions_meta.json").read_text(encoding="utf-8"))
check("short flag written to disk", (meta.get(tok) or {}).get("remember") is False)
check("short flag read back after a restart", c._load_session_meta().get(tok, {}).get("remember") is False)
old = c.new_session("1.2.3.4", "Mozilla/5.0")
check("a session with no flag (made before this change) is remembered", c.session_remembered(old))

# 7. Device list and the sign-in screen
r, tok = login(remember="0")
rows = {x["id"]: x for x in c.list_sessions(tok)}
check("device list marks the short session", rows.get(c.session_id(tok), {}).get("remember") is False)
c.SESSION_META[tok]["last"] = time.time() - c._SHORT_SESSION_IDLE - 60
check("device list hides a short session past its limit",
      c.session_id(tok) not in {x["id"] for x in c.list_sessions()})

html = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
form = html[html.index('id="authOverlay"'):html.index('id="authSubmit"')]
check("sign-in screen has the box, ticked by default",
      'id="authRemember"' in form and 'type="checkbox" id="authRemember" checked' in form)
check("its explanation sits in an (i) block", 'class="info-body" hidden data-i18n="auth.remember_info"' in form)
js = open(os.path.join(ROOT, "dashboard", "app.js"), encoding="utf-8").read()
submit = js[js.index('getElementById("authSubmit").addEventListener'):]
submit = submit[:submit.index("/auth/login")]
check("the sign-in button sends the choice", 'fd.append("remember"' in submit and "authRemember" in submit)
for lang in ("vi", "en"):
    d = json.load(open(os.path.join(ROOT, "dashboard", "i18n", f"{lang}.json"), encoding="utf-8"))
    check(f"{lang}.json has the labels", all(d.get(k) for k in ("auth.remember", "auth.remember_info",
                                                                 "sec.not_remembered")))
# Signing in on a browser that never had a session (the borrowed device) must not open on "your sign-in has expired":
# the refused socket check only says that after this page has seen a valid session.
lost = js[js.index("async function _checkLoginAfterRefusal("):]
lost = lost[:lost.index("\n}\n")]
check("'sign-in expired' only after this page was signed in",
      'if (_authedThisPage && err' in lost and "if (s.authed) { _authedThisPage = true;" in js)
cjs = open(os.path.join(ROOT, "dashboard", "console.js"), encoding="utf-8").read()
check("device list shows the tag", 'x.remember === false' in cjs and 't("sec.not_remembered")' in cjs)

if _fails:
    raise SystemExit(f"{len(_fails)} check(s) failed")
print("all ok")
