"""hPanel's Open button and the free Hostinger name (0.302.0).

    python tests/run.py hostinger_nut_open      (no network: reverse DNS and public IP are stubbed)

Owner report 24/10/2026: after installing on Hostinger, Open led to localhost instead of the VPS link or IP. hPanel's
Open follows the concrete Host(...) rule in the Traefik labels, and the compose put Host(`localhost`) there whenever
DOMAIN_NAME was empty. Checks:
  1. with DOMAIN_NAME empty the labels carry no Host rule and traefik.enable is empty (Open falls back to the
     published port, http://<ip>:7777); with DOMAIN_NAME set they are exactly as before;
  2. the Settings page offers the free srv<id>.hstgr.cloud name from reverse DNS, only for a .hstgr.cloud name.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-open-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. labels, interpolated the way compose does for the forms used here ----
def interp(s, env):
    def one(m):
        name, op, word = m.group(1), m.group(2), m.group(3) or ""
        val = env.get(name, "")
        if op == ":+":
            return word if val else ""
        if op == ":-":
            return val or word
        return val
    return re.sub(r"\$\{([A-Z_]+)(?:(:[+-])([^}]*))?\}", one, s)


labels = yaml.safe_load((ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8"))["services"]["javis"]["labels"]


def rendered(env):
    out = {}
    for x in labels:
        k, _, v = interp(x, env).partition("=")
        out[k] = v
    return out


no = rendered({})
check("no DOMAIN_NAME: no localhost anywhere in the labels", not any("localhost" in v for v in no.values()), no)
check("no DOMAIN_NAME: router rule empty (no concrete Host for Open)", no.get("traefik.http.routers.javis.rule") == "", no)
check("no DOMAIN_NAME: traefik.enable empty (Traefik skips the container)", no.get("traefik.enable") == "", no)
yes = rendered({"DOMAIN_NAME": "javis.srv1.hstgr.cloud"})
check("DOMAIN_NAME set: Host rule for exactly that name",
      yes.get("traefik.http.routers.javis.rule") == "Host(`javis.srv1.hstgr.cloud`)" and yes.get("traefik.enable") == "true", yes)
two = rendered({"DOMAIN_NAME": "b.srv1.hstgr.cloud", "JAVIS_NAME": "javis-b"})
check("second instance keeps its own router name", two.get("traefik.http.routers.javis-b.rule") == "Host(`b.srv1.hstgr.cloud`)", two)
check("the rest of the Traefik labels unchanged",
      yes.get("traefik.http.routers.javis.entrypoints") == "websecure"
      and yes.get("traefik.http.services.javis.loadbalancer.server.port") == "7777")

# ---- 2. the free name ----
from routes import domain as dom   # noqa: E402

S = dom.hostinger_suggestion
check("reverse DNS under .hstgr.cloud gives javis.<name>", S("1.2.3.4", lambda ip: "srv1782015.hstgr.cloud.") == "javis.srv1782015.hstgr.cloud")
check("any other reverse name gives nothing", S("1.2.3.4", lambda ip: "static.vnpt.vn") == "")
check("no IP or a failing lookup gives nothing", S("", lambda ip: "x") == "" and S("1.2.3.4", lambda ip: 1 / 0) == "")
os.environ["JAVIS_NAME"] = "javis-shop"
check("a second instance gets its own sub-name", S("1.2.3.4", lambda ip: "srv1.hstgr.cloud") == "javis-shop.srv1.hstgr.cloud")
os.environ.pop("JAVIS_NAME")

src = (ROOT / "server" / "routes" / "domain.py").read_text(encoding="utf-8")
check("/domain/status returns suggested_domain only while no domain is set",
      '"suggested_domain": suggested' in src and 'if not custom and route_domain in ("", "localhost"):' in src)
js = (ROOT / "dashboard" / "branding.js").read_text(encoding="utf-8")
check("Settings asks the server even with no domain saved", "else { renderDomainStatus({ domain: \"\" }); checkDomain(); }" in js)
check("Settings shows the DOMAIN_NAME line with a copy button", "j.suggested_domain" in js and '"DOMAIN_NAME=" + sg' in js)

# ---- 3. pick_hostinger_name: same rule as the gateway script ----
P = dom.pick_hostinger_name
R = {"srv1.hstgr.cloud": "1.2.3.4", "javis.srv1.hstgr.cloud": "1.2.3.4"}
check("wildcard DNS: <label>.<vps>", P("srv1.hstgr.cloud", "javis", R.get) == "javis.srv1.hstgr.cloud")
check("no wildcard: the VPS name for the default instance", P("srv1.hstgr.cloud", "javis", {"srv1.hstgr.cloud": "1.2.3.4"}.get) == "srv1.hstgr.cloud")
check("no wildcard, second instance: nothing", P("srv1.hstgr.cloud", "javis-b", {"srv1.hstgr.cloud": "1.2.3.4"}.get) == "")
check("label points elsewhere: not offered", P("srv1.hstgr.cloud", "javis", {"srv1.hstgr.cloud": "1.2.3.4", "javis.srv1.hstgr.cloud": "9.9.9.9"}.get) == "srv1.hstgr.cloud")

# ---- 4. /domain/auto: only a link that answers as THIS Javis, Hostinger only ----
import asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app, base_url="http://127.0.0.1:7777")
who = cl.get("/domain/whoami")
check("/domain/whoami is public and returns this process's id", who.status_code == 200 and who.json().get("id") == dom._WHOAMI)
check("auth middleware lists both paths as public", '"/domain/auto", "/domain/whoami"' in (ROOT / "server" / "main.py").read_text(encoding="utf-8"))
os.environ.pop("JAVIS_DEPLOY_TARGET", None)
dom._AUTO.update(url="", ts=0.0)
check("not a Hostinger stack: no link", cl.get("/domain/auto").json() == {"url": ""})
os.environ["JAVIS_DEPLOY_TARGET"] = "hostinger"
seen = []
dom._detect_public_ip = lambda: "1.2.3.4"
dom.hostinger_suggestion = lambda ip, *a, **k: "javis.srv1.hstgr.cloud" if ip == "1.2.3.4" else ""


async def _me(url):
    seen.append(url)
    return ANSWER["v"]


ANSWER = {"v": False}
dom._answers_as_me = _me
dom._AUTO.update(url="", ts=0.0)
check("link does not answer as this Javis: no move", cl.get("/domain/auto").json() == {"url": ""} and seen == ["https://javis.srv1.hstgr.cloud"])
ANSWER["v"] = True
check("the miss is cached a little while (no probe per page load)", cl.get("/domain/auto").json() == {"url": ""} and len(seen) == 1)
dom._AUTO.update(url="", ts=0.0)
check("verified link: the page is told to move there", cl.get("/domain/auto").json() == {"url": "https://javis.srv1.hstgr.cloud"})
os.environ["DOMAIN_NAME"] = "shop.example.com"
dom._AUTO.update(url="", ts=0.0)
check("DOMAIN_NAME set: that link is the one checked", cl.get("/domain/auto").json() == {"url": "https://shop.example.com"} and seen[-1] == "https://shop.example.com")
os.environ.pop("DOMAIN_NAME")
os.environ.pop("JAVIS_DEPLOY_TARGET")

# ---- 5. the page side ----
ad = (ROOT / "dashboard" / "auto-domain.js").read_text(encoding="utf-8")
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("index.html loads auto-domain.js before the app", 0 < html.find("/static/auto-domain.js") < html.find("/static/app.js"))
check("auto-domain.js only moves from a bare IP over http, only to https, ?stay=1 opts out",
      "location.protocol !== \"http:\"" in ad and "^https:\\/\\/[a-z0-9.-]+$" in ad and "stay=1" in ad and "location.replace(" in ad)

for f in ("docker-compose.hostinger.yml", "tests/python/test_hostinger_nut_open.py", "dashboard/auto-domain.js", "server/routes/domain.py"):
    t = (ROOT / f).read_text(encoding="utf-8")
    check("no em or en dash in " + f, chr(0x2014) not in t and chr(0x2013) not in t)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
