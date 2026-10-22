"""Domain setup says which step is broken (0.248.0): routes/domain.py _probe_https / _classify_answer.

    python tests/run.py domain_probe      (no network: httpx is given a fake transport)

Customer report 2026-10-20 (Hostinger): the domain was saved and DNS checked green, but the domain did not open and
Settings only said "SSL: qua Hostinger" with a hint that DNS might be wrong. This file pins:

1. what each answer on https://<domain>/tls-check means: this Javis (valid or not-yet-valid certificate), Traefik's
   "no route" 404, a 502, another Javis, another site, nothing at all;
2. the reason names the Hostinger fix (DOMAIN_NAME / Host line + Redeploy) for "no route";
3. a domain that already answers over HTTPS is never reported as "needs Redeploy", even when DOMAIN_NAME in the
   container env is still "localhost" (owners without an Environment box edit the Host line in the YAML directly).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-domain-probe-test-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx                                  # noqa: E402
from fastapi.testclient import TestClient     # noqa: E402
import config as c                            # noqa: E402
import main                                   # noqa: E402
import routes.domain as dom                   # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


cl = TestClient(main.app, client=("127.0.0.1", 50000), base_url="http://localhost:7777")
DOMAIN = "javis.tisavn.com"
c.update_settings({"domain": {"custom": DOMAIN}})

# The real answers, taken from the app itself rather than typed by hand.
mine = cl.get(f"/tls-check?domain={DOMAIN}")
other = cl.get("/tls-check?domain=khac.example.com")
check("this Javis answers 200 for its own domain", mine.status_code == 200, mine.text)
check("and 403 for a domain it does not hold", other.status_code == 403, other.text)
TRAEFIK_404 = "404 page not found\n"   # Traefik's body when no router matches the Host

# ============================================================
# 1. Classifier
# ============================================================
cases = [
    ("this Javis, valid certificate -> ok", (200, mine.text, True), "ok"),
    ("this Javis behind a bad certificate -> cert_pending", (200, mine.text, False), "cert_pending"),
    ("Traefik 404 -> no_route (verified)", (404, TRAEFIK_404, True), "no_route"),
    ("Traefik 404 behind its default certificate -> no_route", (404, TRAEFIK_404, False), "no_route"),
    ("another Javis (403 JSON) -> other_javis", (403, other.text, True), "other_javis"),
    ("502 from the proxy -> bad_gateway", (502, "Bad Gateway", True), "bad_gateway"),
    ("some other web page -> other_site", (200, "<html>Welcome to nginx</html>", True), "other_site"),
    ("other page behind a bad certificate -> cert_invalid", (200, "<html>parked</html>", False), "cert_invalid"),
    ("an app 404 page is not Traefik's -> other_site", (404, "<html>Not found</html>", True), "other_site"),
]
for name, args, want in cases:
    got = dom._classify_answer(*args)
    check(name, got == want, got)
check("every code has a reason", all(dom._probe_reason(k, True) and dom._probe_reason(k, False)
                                     for k in dom.PROBE_CODES))
reason = dom._probe_reason("no_route", True)
check("no_route on Hostinger names DOMAIN_NAME, the Host line and Redeploy",
      "DOMAIN_NAME" in reason and "Host" in reason and "Redeploy" in reason, reason)

# ============================================================
# 2. The probe itself, with a fake network
# ============================================================
_real_client = httpx.AsyncClient


def fake_network(verified_answer, unverified_answer=None, seen=None):
    """Patch httpx.AsyncClient: verified requests get `verified_answer`, verify=False ones `unverified_answer`.
    An answer is (status, body) or an exception to raise."""
    def factory(*args, **kw):
        answer = unverified_answer if kw.get("verify", True) is False else verified_answer

        def handler(request):
            if seen is not None:
                seen.append(str(request.url))
            if isinstance(answer, Exception):
                raise answer
            return httpx.Response(answer[0], text=answer[1])
        kw.pop("verify", None)
        return _real_client(*args, transport=httpx.MockTransport(handler), **kw)
    httpx.AsyncClient = factory


def probe(hostinger=True):
    try:
        return asyncio.run(dom._probe_https(DOMAIN, hostinger=hostinger))
    finally:
        httpx.AsyncClient = _real_client


ssl_err = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate")
seen = []
fake_network((200, mine.text), seen=seen)
active, why, code = probe()
check("working domain -> active, ok", active and code == "ok", (active, code))
check("the probe asks /tls-check for this domain",
      seen and seen[0] == f"https://{DOMAIN}/tls-check?domain={DOMAIN}", seen)

fake_network(ssl_err, (404, TRAEFIK_404))
active, why, code = probe()
check("Traefik default cert + 404 behind it -> no_route (the customer's case)", not active and code == "no_route", code)

fake_network(ssl_err, (200, mine.text))
active, why, code = probe()
check("bad certificate but Javis behind it -> cert_pending", not active and code == "cert_pending", code)

fake_network(ssl_err, ssl_err)
active, why, code = probe()
check("certificate refused even unverified -> cert_invalid", not active and code == "cert_invalid", code)

fake_network(httpx.ConnectError("[Errno 111] Connection refused"))
active, why, code = probe(hostinger=False)
check("nothing on 443 -> unreachable, Caddy wording off Hostinger", code == "unreachable" and "Caddy" in why, why)

# ============================================================
# 3. /domain/status on Hostinger
# ============================================================
os.environ["JAVIS_DEPLOY_TARGET"] = "hostinger"
os.environ["DOMAIN_NAME"] = "localhost"
_real_probe = dom._probe_https


async def probe_says(code):
    return code == "ok", dom._probe_reason(code, True), code


dom._probe_https = lambda d, hostinger=False: probe_says("ok")
st = cl.get("/domain/status").json()
check("Host line edited in YAML, DOMAIN_NAME still localhost, HTTPS works -> no 'needs Redeploy'",
      st["ssl_active"] is True and st["requires_redeploy"] is False and st["ssl_code"] == "ok", st)

dom._probe_https = lambda d, hostinger=False: probe_says("no_route")
st = cl.get("/domain/status").json()
check("no route and DOMAIN_NAME differs -> needs Redeploy, code no_route",
      st["requires_redeploy"] is True and st["ssl_code"] == "no_route" and st["ssl_active"] is False, st)

os.environ["DOMAIN_NAME"] = DOMAIN
st = cl.get("/domain/status").json()
check("DOMAIN_NAME already right but Traefik still has no route -> reason explains the Host line",
      st["requires_redeploy"] is False and st["ssl_code"] == "no_route" and "Host" in st["ssl_reason"], st)

dom._probe_https = _real_probe

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_domain_probe: all pass")
