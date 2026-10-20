"""Local-only login exemptions refuse requests that arrive through a tunnel or proxy (0.253.0, security).

    python tests/python/test_local_exempt_tunnel.py

/reminders, /reminders/cancel, /reminders/update and /telegram/send-file skip the login so the engines and the
javis_schedule plugin can call them from this machine. The check used to look at the client address only, but the
built-in Cloudflare Tunnel, Tailscale serve and a reverse proxy on a VPS all connect from 127.0.0.1: anyone with the
tunnel URL could create a task or script reminder at the full permission level without logging in. Found while
reviewing PR #733. No network.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tunnel-")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


main.cfgmod.gate_active = lambda: True          # a password is set (the tunnel only runs with one)
main.cfgmod.auth_enabled = lambda: True

local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))
remote = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("203.0.113.9", 50000))
HOPS = {"cf-connecting-ip": "198.51.100.7", "x-forwarded-for": "198.51.100.7", "x-real-ip": "198.51.100.7",
        "forwarded": "for=198.51.100.7"}
BODY = {"text": "x", "delay_min": 5, "mode": "task", "muc_quyen": "full", "brain": "brain"}

for path in main._AUTH_LOCAL_EXACT:
    r = local.post(path, json=BODY if path == "/reminders" else {})
    check(f"{path}: a direct call from this machine still skips the login", r.status_code != 401, r.status_code)
    for h, v in HOPS.items():
        r = local.post(path, json=BODY, headers={h: v})
        check(f"{path}: 127.0.0.1 with {h} (tunnel / proxy) needs the login", r.status_code == 401, r.status_code)
    r = remote.post(path, json=BODY)
    check(f"{path}: another address needs the login", r.status_code == 401, r.status_code)

src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
check("_auth_guard asks _direct_local_request, not the bare client address",
      "or (path in _AUTH_LOCAL_EXACT and _direct_local_request(request))" in src
      and 'path in _AUTH_LOCAL_EXACT and client_host in ("127.0.0.1", "::1")' not in src)
check("the forwarding headers include the Cloudflare one", "cf-connecting-ip" in main._FORWARD_HEADERS)

print()
if _fails:
    print(f"FAIL {len(_fails)} test")
    sys.exit(1)
print("TẤT CẢ PASS")
