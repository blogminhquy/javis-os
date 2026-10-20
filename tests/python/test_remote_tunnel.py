"""Remote access through the built-in Cloudflare Tunnel (0.242.0): server/remote_tunnel.py + routes/remote_access.py.

    python tests/run.py remote_tunnel      (no network: a fake cloudflared script stands in for the real one)

Owner request 2026-10-20: someone running Javis on Windows or macOS fills in a form in Settings and reaches Javis from
anywhere. This file pins what that must and must not do:

1. the token is found inside whatever the owner pastes (bare, or Cloudflare's install command), the right release file
   is picked per OS/CPU, and the log lines that carry the link are read correctly;
2. the token is stored encrypted, never returned by GET /settings, and reaches cloudflared through the environment,
   not argv;
3. the tunnel never starts without a password, stops by itself when the password goes away, and while it is on,
   login cannot be turned off;
4. turning it on and off from the dashboard really starts and stops the process, and a stray one from an earlier run
   is killed;
5. Tailscale mode (0.244.0) refuses without an installed, signed-in Tailscale, shows the "enable HTTPS" link and
   retries by itself, switches `tailscale serve` off on disable, mode switch and password loss, and keeps it across a
   server restart.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-remote-tunnel-test-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_HOST", None)
os.environ.pop("JAVIS_PORT", None)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient   # noqa: E402
import config as c                           # noqa: E402
import main                                  # noqa: E402
import remote_tunnel as rt                   # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def wait_for(pred, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return pred()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:   # a zombie still answers kill(0); it is dead for our purpose
        st = Path(f"/proc/{pid}/stat").read_text().split()
        return st[2] != "Z"
    except Exception:
        return True


TOKEN = base64.b64encode(json.dumps({"a": "acc0123456789", "t": "1234abcd-0000-4000-8000-feedfacecafe",
                                     "s": base64.b64encode(b"x" * 32).decode()}).encode()).decode()

# ============================================================
# 1. Pure helpers
# ============================================================
check("bare token is recognised", rt.extract_token(TOKEN) == TOKEN)
check("token inside the Windows install command",
      rt.extract_token(f"cloudflared.exe service install {TOKEN}") == TOKEN)
check("token inside the macOS command with brew and sudo",
      rt.extract_token(f"brew install cloudflared && \nsudo cloudflared service install {TOKEN}") == TOKEN)
check("token inside a docker run line",
      rt.extract_token(f"docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token {TOKEN}") == TOKEN)
check("garbage gives no token", rt.extract_token("cloudflared service install hello eyJhbGciOiJIUzI1NiJ9.abc.def") == "")
check("token_info reads the tunnel id", (rt.token_info(TOKEN) or {}).get("tunnel_id", "").startswith("1234abcd"))

check("Windows x64 -> windows-amd64.exe", rt.asset_name("Windows", "AMD64") == "cloudflared-windows-amd64.exe")
check("Windows on ARM -> windows-arm64.exe", rt.asset_name("Windows", "ARM64") == "cloudflared-windows-arm64.exe")
check("Apple Silicon -> darwin-arm64.tgz", rt.asset_name("Darwin", "arm64") == "cloudflared-darwin-arm64.tgz")
check("Intel Mac -> darwin-amd64.tgz", rt.asset_name("Darwin", "x86_64") == "cloudflared-darwin-amd64.tgz")
check("Linux x64 -> linux-amd64", rt.asset_name("Linux", "x86_64") == "cloudflared-linux-amd64")
check("unknown platform -> no file", rt.asset_name("Plan9", "mips") == "")

box = "2026-10-20T03:47:15Z INF |  https://brave-tiny-otter.trycloudflare.com                          |"
check("quick link read from the box cloudflared prints", rt.parse_quick_url(box) == "https://brave-tiny-otter.trycloudflare.com")
check("the request to api.trycloudflare.com is not taken for the link",
      rt.parse_quick_url('failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel"') == "")
cfg_line = ('2026-10-20T03:47:15Z INF Updated to new configuration config="{\\"ingress\\":[{\\"hostname\\":'
            '\\"Javis.Example.com\\", \\"service\\":\\"http://localhost:7777\\"}, {\\"service\\":\\"http_status:404\\"}],'
            ' \\"warp-routing\\":{\\"enabled\\":false}}" version=3')
check("hostname and service read from a token tunnel's config line",
      rt.parse_ingress(cfg_line) == [("javis.example.com", "http://localhost:7777")])
check("an unrelated line is not a config line", rt.parse_ingress("INF Starting tunnel") is None)
check("localhost:7777 points at this Javis", rt.service_points_here("http://localhost:7777"))
check("127.0.0.1:7777 points at this Javis", rt.service_points_here("http://127.0.0.1:7777"))
check("another port does not", not rt.service_points_here("http://localhost:8080"))
check("another machine does not", not rt.service_points_here("http://192.168.1.5:7777"))
check("default target is loopback on the Javis port", rt.local_target() == "http://127.0.0.1:7777")

# ============================================================
# 2. Settings: encrypted at rest, hidden from GET /settings, forces login
# ============================================================
check("login not required before the tunnel is on (JAVIS_REQUIRE_LOGIN=0)", c.require_login() is False)
c.update_settings({"remote_tunnel": {"enabled": False, "mode": "token", "token": TOKEN}})
raw = json.loads(c.SETTINGS_PATH.read_text(encoding="utf-8"))
check("token stored encrypted on disk", str(raw.get("remote_tunnel", {}).get("token", "")).startswith("enc:"))
check("token decrypts back", c.read_settings()["remote_tunnel"]["token"] == TOKEN)
check("GET /settings does not carry the token", TOKEN not in json.dumps(main.settings_get()))
c.update_settings({"remote_tunnel": {"enabled": True}})
check("tunnel on -> login required, even over JAVIS_REQUIRE_LOGIN=0", c.require_login() is True)
c.update_settings({"remote_tunnel": {"enabled": False, "token": ""}})

# ============================================================
# 3. Routes and supervisor, with a fake cloudflared
# ============================================================
work = Path(tempfile.mkdtemp(prefix="javis-fake-cf-"))
calls = work / "calls.log"
fake = work / "cloudflared"
fake.write_text(f"""#!{sys.executable}
import os, sys, time
args = sys.argv[1:]
with open({str(calls)!r}, "a") as f:
    f.write(" ".join(args) + "|" + os.environ.get("TUNNEL_TOKEN", "") + "\\n")
if "--url" in args:
    print("INF |  https://brave-tiny-otter.trycloudflare.com   |", flush=True)
else:
    print({cfg_line!r}, flush=True)
print("INF Registered tunnel connection connIndex=0 location=sin01", flush=True)
time.sleep(120)
""")
fake.chmod(0o755)
rt.MANAGER._find = lambda: str(fake)
rt.MANAGER._install = lambda: (_ for _ in ()).throw(AssertionError("must not download in this test"))
rt.PASSWORD_CHECK_EVERY = 1

cl = TestClient(main.app, client=("127.0.0.1", 50000), base_url="http://localhost:7777")
PW = "matkhau123"

r = cl.post("/remote-access/enable", data={"mode": "quick"})
check("no password -> 409 need_password, nothing started",
      r.status_code == 409 and r.json().get("need_password") and rt.MANAGER._proc is None)

cfg = c.read_settings()
cfg["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"), c.hash_password(PW)))}
c.write_settings(cfg)
main._LOGIN_FAILS.clear()
r = cl.post("/auth/login", data={"username": "admin", "password": PW})
check("signed in", r.json().get("ok") is True)

tok_api = c.create_api_token("t", "full")["token"]
_cookies = dict(cl.cookies)
cl.cookies.clear()
r = cl.post("/remote-access/enable", data={"mode": "quick"}, headers={"Authorization": f"Bearer {tok_api}"})
check("API token -> 403 (only a browser session may open the machine)", r.status_code == 403)
for k, v in _cookies.items():
    cl.cookies.set(k, v)

r = cl.post("/remote-access/enable", data={"mode": "quick"})
check("quick mode accepted", r.status_code == 200 and r.json().get("ok"), r.text)
check("quick mode reaches running with the trycloudflare link",
      wait_for(lambda: rt.MANAGER.status()["state"] == "running" and rt.MANAGER.status()["url"].endswith(".trycloudflare.com")))
first = calls.read_text().splitlines()[-1]
check("quick mode points cloudflared at this server", "--url http://127.0.0.1:7777" in first and "--no-autoupdate" in first, first)
pid_quick = rt.MANAGER._proc.pid
check("pid file written", (Path(c.STATE_DIR) / "remote-tunnel.pid").read_text().strip() == str(pid_quick))

r = cl.post("/auth/disable", data={"password": PW})
check("login cannot be turned off while the tunnel is on", r.status_code == 403 and c.auth_enabled())

r = cl.post("/remote-access/enable", data={"mode": "token", "token": "not a token at all"})
check("a paste without a token -> 400", r.status_code == 400)
r = cl.post("/remote-access/enable", data={"mode": "token", "token": f"cloudflared.exe service install {TOKEN}"})
check("token mode accepted from the pasted install command", r.status_code == 200 and r.json().get("ok"), r.text)
check("the quick tunnel was stopped before the named one started", wait_for(lambda: not alive(pid_quick), 5))
check("token mode reaches running with the owner's hostname",
      wait_for(lambda: rt.MANAGER.status()["url"] == "https://javis.example.com"
               and rt.MANAGER.status()["state"] == "running"))
last = calls.read_text().splitlines()[-1]
argv, env_token = last.split("|", 1)
check("token passed through TUNNEL_TOKEN", env_token == TOKEN)
check("token NOT on the command line", TOKEN not in argv and argv.startswith("tunnel --no-autoupdate run"), argv)
st = rt.MANAGER.status()
check("status shows the tunnel id, never the token", st["has_token"] and st["tunnel_id"] == "1234abcd"
      and TOKEN not in json.dumps(st))
check("service matches this Javis: no mismatch warning", st["service_mismatch"] == [])

r = cl.post("/remote-access/enable", data={"mode": "token"})
check("re-enable with an empty box keeps the saved token", r.status_code == 200 and c.read_settings()["remote_tunnel"]["token"] == TOKEN)
check("and runs again", wait_for(lambda: rt.MANAGER.status()["state"] == "running"))

# The password disappears (reset-auth while running): the supervisor must take the machine off the Internet.
pid_named = rt.MANAGER._proc.pid
cfg = c.read_settings()
cfg["auth"] = {"username": "admin"}
c.write_settings(cfg)
check("password removed -> cloudflared stopped within seconds", wait_for(lambda: not alive(pid_named), 8))
_why = rt.MANAGER.status()["error"].lower() if wait_for(lambda: rt.MANAGER.status()["state"] == "error") else ""
check("... and the status says why", "mật khẩu" in _why or "password" in _why, _why)

# Back with a password, then turned off from the dashboard.
cfg = c.read_settings()
cfg["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"), c.hash_password(PW)))}
c.write_settings(cfg)
main._LOGIN_FAILS.clear()
cl.cookies.clear()
cl.post("/auth/login", data={"username": "admin", "password": PW})
r = cl.post("/remote-access/enable", data={"mode": "quick"})
check("on again", r.status_code == 200 and wait_for(lambda: rt.MANAGER.status()["state"] == "running"))
pid_last = rt.MANAGER._proc.pid
r = cl.post("/remote-access/disable")
check("turned off -> state off and process gone",
      r.status_code == 200 and r.json().get("state") == "off" and wait_for(lambda: not alive(pid_last), 5))
check("turned off -> pid file removed", not (Path(c.STATE_DIR) / "remote-tunnel.pid").exists())
check("turned off -> login rule back to normal", c.require_login() is False)

# ============================================================
# 4. Tailscale mode (0.244.0), with a fake tailscale CLI
# ============================================================
ts_state = work / "ts_state.json"
ts_calls = work / "ts_calls.log"
fake_ts = work / "tailscale"
fake_ts.write_text(f"""#!{sys.executable}
import json, sys, time
args = sys.argv[1:]
st = json.load(open({str(ts_state)!r}))
with open({str(ts_calls)!r}, "a") as f:
    f.write(" ".join(args) + "\\n")
if args[:2] == ["status", "--json"]:
    print(json.dumps({{"BackendState": st["backend"],
                      "Self": {{"DNSName": "May-Cua-Quy.tail1234.ts.net.", "TailscaleIPs": ["100.101.102.103"]}}}}))
elif args and args[0] == "serve":
    if args[-1] == "off":
        sys.exit(0)
    if not st["https"]:
        print("Serve is not enabled on your tailnet.\\nTo enable, visit:\\n\\n    https://login.tailscale.com/f/serve?node=n123abc\\n", flush=True)
        time.sleep(60)
    print("Available within your tailnet:\\n\\nhttps://may-cua-quy.tail1234.ts.net/\\n|-- proxy " + args[-1])
""")
fake_ts.chmod(0o755)


def ts_set(backend="Running", https=True):
    ts_state.write_text(json.dumps({"backend": backend, "https": https}))
    rt.MANAGER._ts_cache = (0.0, None)


def ts_lines():
    return ts_calls.read_text().splitlines() if ts_calls.exists() else []


def serve_offs():
    return sum(1 for x in ts_lines() if x == "serve --https=443 off")


rt.TS_SERVE_TIMEOUT = 2
rt.TS_RETRY_EVERY = 1
ts_set()
info = rt.tailscale_info(str(fake_ts))
check("tailscale_info reads state, name and IP",
      info == {"installed": True, "backend": "Running", "dns_name": "may-cua-quy.tail1234.ts.net", "ip": "100.101.102.103"}, info)
check("tailscale_info without a binary says not installed", rt.tailscale_info("")["installed"] is False)

rt.MANAGER._ts_find = lambda: ""
rt.MANAGER._ts_cache = (0.0, None)
r = cl.post("/remote-access/enable", data={"mode": "tailscale"})
check("tailscale not installed -> 409 need_tailscale", r.status_code == 409 and r.json().get("need_tailscale"))
check("status says not installed", rt.MANAGER.status()["tailscale"]["installed"] is False)

rt.MANAGER._ts_find = lambda: str(fake_ts)
ts_set(backend="NeedsLogin")
r = cl.post("/remote-access/enable", data={"mode": "tailscale"})
check("tailscale signed out -> 409 need_tailscale_login", r.status_code == 409 and r.json().get("need_tailscale_login"))

ts_set(backend="Running", https=False)
r = cl.post("/remote-access/enable", data={"mode": "tailscale"})
check("tailscale mode accepted", r.status_code == 200 and r.json().get("ok"), r.text)
check("HTTPS not enabled yet -> waiting with the enable link",
      wait_for(lambda: rt.MANAGER.status()["enable_url"] == "https://login.tailscale.com/f/serve?node=n123abc"
               and rt.MANAGER.status()["state"] == "waiting", 10))
ts_set(backend="Running", https=True)
check("owner enables HTTPS -> Javis retries by itself and runs on the ts.net link",
      wait_for(lambda: rt.MANAGER.status()["state"] == "running"
               and rt.MANAGER.status()["url"] == "https://may-cua-quy.tail1234.ts.net", 15))
check("serve points tailscaled at this server on :443",
      "serve --bg --https=443 http://127.0.0.1:7777" in ts_lines(), ts_lines()[-3:])
check("no cloudflared started in tailscale mode", rt.MANAGER._proc is None or rt.MANAGER._proc.poll() is not None)

offs = serve_offs()
cfg = c.read_settings()
cfg["auth"] = {"username": "admin"}
c.write_settings(cfg)
check("password removed -> tailscale serve switched off", wait_for(lambda: serve_offs() > offs, 8))
check("... and state error", wait_for(lambda: rt.MANAGER.status()["state"] == "error"))

cfg = c.read_settings()
cfg["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"), c.hash_password(PW)))}
c.write_settings(cfg)
main._LOGIN_FAILS.clear()
cl.cookies.clear()
cl.post("/auth/login", data={"username": "admin", "password": PW})
r = cl.post("/remote-access/enable", data={"mode": "tailscale"})
check("tailscale on again", r.status_code == 200 and wait_for(lambda: rt.MANAGER.status()["state"] == "running"))
offs = serve_offs()
r = cl.post("/remote-access/enable", data={"mode": "quick"})
check("switching to Quick link switches serve off", r.status_code == 200 and serve_offs() == offs + 1)
check("... and the quick tunnel runs", wait_for(lambda: rt.MANAGER.status()["state"] == "running"
                                                 and rt.MANAGER.status()["url"].endswith(".trycloudflare.com")))

r = cl.post("/remote-access/enable", data={"mode": "tailscale"})
check("back to tailscale", r.status_code == 200 and wait_for(lambda: rt.MANAGER.status()["mode"] == "tailscale"
                                                              and rt.MANAGER.status()["state"] == "running"))
offs = serve_offs()
rt.MANAGER.stop(wait=3, keep_serve=True)
check("server shutdown keeps the serve entry (it lives in tailscaled)", serve_offs() == offs)
rt.MANAGER.start()
check("restart re-applies it", wait_for(lambda: rt.MANAGER.status()["state"] == "running"))
r = cl.post("/remote-access/disable")
check("turned off -> serve switched off", r.status_code == 200 and serve_offs() == offs + 1
      and r.json().get("state") == "off")

# ============================================================
# 5. A cloudflared left behind by an earlier run is killed on start
# ============================================================
stray = subprocess.Popen([str(fake), "tunnel", "--url", "http://127.0.0.1:7777"], stdout=subprocess.DEVNULL)
(Path(c.STATE_DIR) / "remote-tunnel.pid").write_text(str(stray.pid))
time.sleep(0.3)
check("stray cloudflared is killed", rt.kill_stray() is True and wait_for(lambda: stray.poll() is not None, 5))
other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
(Path(c.STATE_DIR) / "remote-tunnel.pid").write_text(str(other.pid))
check("a pid that is not cloudflared is left alone", rt.kill_stray() is False and other.poll() is None)
other.kill()

rt.MANAGER.stop()
if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_remote_tunnel: all pass")
