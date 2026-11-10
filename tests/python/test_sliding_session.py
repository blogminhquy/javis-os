"""A sign-in session stays alive while it is used (sliding expiry).

    python tests/run.py sliding_session      (no network)

Reported 2026-11-10: chat images stopped loading on the owner's PC tab. The session had been created exactly 30 days
earlier and expired then however often Javis was used; the browser dropped the cookie at the same moment. The open tab
kept chatting over its WebSocket while every HTTP call, images included, got 401.

Contract:
1. A session younger than a day is not rewritten (no disk write per request).
2. A live session older than a day gets a fresh timestamp, so it lives 30 more days.
3. An expired or unknown session is never revived.
4. The device list keeps showing the original sign-in time.
5. The auth guard re-issues the cookie on renewal, but not once the request ended the session (/auth/logout).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sliding-")

import config as c   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


t = c.new_session()
check("fresh session is valid", c.valid_session(t))
check("fresh session is not renewed", not c.renew_session(t))

signed_in = time.time() - 29 * 86400
c.SESSIONS[t] = signed_in
check("29-day-old session is renewed", c.renew_session(t))
check("renewed session carries a fresh timestamp", time.time() - c.SESSIONS[t] < 5)
check("a second call the same day does nothing", not c.renew_session(t))
c.SESSIONS[t] -= 2 * 86400   # day 31 since sign-in, used on day 29
check("used on day 29, still valid on day 31", c.valid_session(t))
row = [r for r in c.list_sessions() if r["id"] == c.session_id(t)]
check("device list keeps the original sign-in time", bool(row) and abs(row[0]["created"] - signed_in) < 2)
check("renewal survives a restart (written to disk)",
      t in __import__("json").loads((c.STATE_DIR / ".sessions.json").read_text(encoding="utf-8")))

old = c.new_session()
c.SESSIONS[old] = time.time() - 31 * 86400
check("expired session is not revived", not c.renew_session(old))
check("expired session stays invalid", not c.valid_session(old))
check("unknown or empty token is not renewed", not c.renew_session("nope") and not c.renew_session(""))

src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
guard = src[src.index("async def _auth_guard"):src.index("def _bearer(")]
check("auth guard renews the session", "cfgmod.renew_session(" in guard)
check("auth guard re-issues the cookie only while the session is still valid",
      "if renewed and cfgmod.valid_session(renewed):" in guard and "_session_cookie(resp, renewed, request)" in guard)

if _fails:
    raise SystemExit(f"{len(_fails)} check(s) failed")
print("all ok")
