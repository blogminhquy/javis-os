"""One Hostinger compose link that gets HTTPS with or without Hostinger's Traefik (0.300.0).

    python tests/run.py hostinger_khong_traefik      (no Docker needed: the gateway script runs under sh with stubs)

Owner question 24/10/2026: the "Ubuntu 24 + Docker" template on Hostinger ships Traefik on ports 80/443, a plain
Ubuntu 26 does not, so the same link gave Javis but never HTTPS. The `gateway` service in docker-compose.hostinger.yml
runs Caddy only when 80/443 are free. Checks:
  1. the service shape: host networking (never publishes 80/443, so a Traefik VPS never gets "port is already
     allocated"), no new Environment field, Traefik ignores it, certificates kept in a volume;
  2. the script itself, run with stubs: no DOMAIN_NAME -> idle; a bad DOMAIN_NAME -> idle; ports busy -> idle and says
     Traefik has it; ports free -> writes a Caddyfile for exactly DOMAIN_NAME to JAVIS_HOST_PORT and starts Caddy.
Verified once by hand on Docker 29 (2026-10-24): idle without a domain, Caddy answering 308 then 200 through to the
app when the ports were free, idle next to a container holding 80/443.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


src = (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
doc = yaml.safe_load(src)
gw = doc["services"].get("gateway") or {}

# ---- 1. shape ----
check("the Hostinger compose has a gateway service", bool(gw))
check("host networking, never publishes ports (no clash with Traefik)", gw.get("network_mode") == "host" and "ports" not in gw)
check("Caddy image", str(gw.get("image", "")).startswith("caddy:2"))
check("only DOMAIN_NAME, JAVIS_HOST_PORT, JAVIS_NAME, all already in the form",
      set((gw.get("environment") or {}).keys()) == {"DOMAIN_NAME", "JAVIS_HOST_PORT", "JAVIS_NAME"})
check("named after the instance like the other containers", gw.get("container_name") == "${JAVIS_NAME:-javis}-gateway")
check("Traefik ignores it", "traefik.enable=false" in (gw.get("labels") or []))
check("certificates kept in a volume across Redeploy",
      any(str(v).startswith("gateway-data:/data") for v in gw.get("volumes") or []) and "gateway-data" in (doc.get("volumes") or {}))
check("restarts with the stack", gw.get("restart") == "unless-stopped")
check("the javis service still carries the Traefik labels for Ubuntu 24",
      any("traefik.http.routers" in str(x) for x in doc["services"]["javis"].get("labels") or []))

# ---- 2. the script, with stubs ----
script = gw["entrypoint"][2].replace("$$", "$")
SH = shutil.which("sh")


def run(env_domain, busy=False, port="7777", host="vm", dns=None, name=None):
    d = Path(tempfile.mkdtemp(prefix="gw-"))
    (d / "bin").mkdir()
    (d / "config").mkdir()
    tcp = d / "tcp"
    line = "  0: 00000000:01BB 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 1 1" if busy else \
           "  0: 0100007F:1E61 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 1 1"
    tcp.write_text("  sl  local_address rem_address   st\n" + line + "\n")
    (d / "bin" / "nc").write_text("#!/bin/sh\nexit 1\n")
    (d / "bin" / "caddy").write_text(f"#!/bin/sh\necho CADDY \"$@\" > {d}/caddy.log\n")
    (d / "bin" / "sleep").write_text("#!/bin/sh\nexit 9\n")   # the idle loops end at once instead of waiting
    # 0.302.0: the VPS hostname and DNS answers the gateway sees (uts: host + getent).
    (d / "bin" / "hostname").write_text(f"#!/bin/sh\necho {host}\n")
    lines = "".join(f'  {k}) echo "{v} {k}";;\n' for k, v in (dns or {}).items())
    (d / "bin" / "getent").write_text(f'#!/bin/sh\ncase "$2" in\n{lines}  *) exit 2;;\nesac\n')
    for f in ("nc", "caddy", "sleep", "hostname", "getent"):
        (d / "bin" / f).chmod(0o755)
    s = (script.replace("/proc/net/tcp6", str(d / "none")).replace("/proc/net/tcp", str(tcp))
         .replace("/config/Caddyfile", str(d / "config" / "Caddyfile")).replace("/status", str(d / "status")))
    s = s.replace("while :; do sleep 3600; done", "sleep 3600; exit 0").replace("sleep 600", "sleep 600; exit 0")
    env = dict(os.environ, PATH=f"{d}/bin:" + os.environ.get("PATH", ""), JAVIS_HOST_PORT=port)
    if env_domain is not None:
        env["DOMAIN_NAME"] = env_domain
    if name is not None:
        env["JAVIS_NAME"] = name
    p = subprocess.run([SH, "-c", s], env=env, capture_output=True, text=True, timeout=20)
    caddyfile = (d / "config" / "Caddyfile").read_text() if (d / "config" / "Caddyfile").exists() else ""
    caddy = (d / "caddy.log").read_text() if (d / "caddy.log").exists() else ""
    st = d / "status" / "gateway.txt"
    STATUS["v"] = st.read_text() if st.exists() else ""
    return p.stdout, caddyfile, caddy


STATUS = {"v": ""}


if SH:
    out, cf, cd = run(None)
    check("no DOMAIN_NAME: idle, says how to reach Javis", "DOMAIN_NAME chua dat" in out and not cd, out)
    out, cf, cd = run("localhost")
    check("DOMAIN_NAME=localhost (the default): idle", "DOMAIN_NAME chua dat" in out and not cd)
    out, cf, cd = run("bad domain;rm")
    check("a DOMAIN_NAME with odd characters never reaches the Caddyfile", "khong hop le" in out and not cf and not cd, out)
    out, cf, cd = run("javis.srv1.hstgr.cloud", busy=True)
    check("80/443 held by another proxy: idle and says Traefik has it", "Traefik" in out and not cd, out)
    check("busy: the status file says so, with the name", STATUS["v"] == "state=busy\nnames=javis.srv1.hstgr.cloud\n", STATUS["v"])
    out, cf, cd = run("javis.srv1.hstgr.cloud", port="7778")
    check("ports free: Caddyfile for exactly DOMAIN_NAME to the instance's host port",
          cf.strip() == "javis.srv1.hstgr.cloud {\n\treverse_proxy 127.0.0.1:7778\n}", repr(cf))
    check("ports free: Caddy starts with that file", "run --config" in cd and "--adapter caddyfile" in cd, cd)
    check("serving: the status file lists the name", STATUS["v"] == "state=serving\nnames=javis.srv1.hstgr.cloud\n", STATUS["v"])
    check("serving: the log names the firewall as the thing to check", "Tuong lua" in out, out)
    # 0.302.0/0.304.0: no DOMAIN_NAME on a Hostinger VPS -> the VPS link. 0.304.0 serves BOTH javis.<vps> and <vps> and
    # never asks DNS, because getent read the VPS's /etc/hosts (hostname -> 127.0.1.1) and picked a different name
    # from the one Javis checked (owner report 24/10/2026, Ubuntu 26: still IP, no https).
    out, cf, cd = run(None, host="srv1782015.hstgr.cloud", dns={"srv1782015.hstgr.cloud": "127.0.1.1"})
    check("no DOMAIN_NAME: Caddy serves javis.<vps> and <vps>, /etc/hosts makes no difference",
          cf.startswith("javis.srv1782015.hstgr.cloud, srv1782015.hstgr.cloud {") and "run --config" in cd, (out, cf))
    check("the status file lists both, javis.<vps> first",
          STATUS["v"] == "state=serving\nnames=javis.srv1782015.hstgr.cloud srv1782015.hstgr.cloud\n", STATUS["v"])
    out, cf, cd = run("localhost", host="srv1782015.hstgr.cloud")
    check("DOMAIN_NAME=localhost acts as unset", cf.startswith("javis.srv1782015.hstgr.cloud, srv1782015.hstgr.cloud {"), (out, cf))
    out, cf, cd = run(None, host="SRV1782015")
    check("a short srv<id> hostname gets .hstgr.cloud (and lower case)",
          cf.startswith("javis.srv1782015.hstgr.cloud, srv1782015.hstgr.cloud {"), (out, cf))
    out, cf, cd = run(None, host="srv1782015.hstgr.cloud", name="javis-shop")
    check("second instance: only its own sub-name, never the bare VPS name",
          cf.startswith("javis-shop.srv1782015.hstgr.cloud {"), (out, cf))
    out, cf, cd = run(None, host="srv1782015.hstgr.cloud", busy=True)
    check("Traefik holding 80/443: idle even with a VPS name", not cd and "Traefik" in out, out)
    check("Traefik holding 80/443: status busy", STATUS["v"].startswith("state=busy\n"), STATUS["v"])
    out, cf, cd = run(None, host="my-laptop")
    check("not a Hostinger hostname: idle", not cd and "DOMAIN_NAME chua dat" in out, out)
    check("idle: status file says idle", STATUS["v"] == "state=idle\nnames=\n", STATUS["v"])
    check("gateway shares the VPS hostname (uts: host)", gw.get("uts") == "host")
    jv = doc["services"]["javis"]
    check("the status volume: gateway writes, javis reads only",
          "gateway-status:/status" in (gw.get("volumes") or []) and "gateway-status:/gateway:ro" in (jv.get("volumes") or [])
          and "gateway-status" in (doc.get("volumes") or {}))
else:
    print("skip script run (no sh)")

for f in ("docker-compose.hostinger.yml", "tests/python/test_hostinger_khong_traefik.py"):
    t = (ROOT / f).read_text(encoding="utf-8")
    check("no em or en dash in " + f, chr(0x2014) not in t and chr(0x2013) not in t)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
