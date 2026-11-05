"""Low-severity security fixes from the 2026-11-05 audit. Run by hand / CI:

    python tests/python/test_va_bao_mat_thap_2026_11_05.py

No network.

 14. Public paths: "/health" is public as an exact path only, so /health/loop (stack traces, server paths) needs the
     login; the static mount keeps a prefix WITH its slash.
 15. A "chat" scope API token reaches /chat and what lies under it, never /chatbots.
 16. WhatsApp: a second customer file with the same name no longer overwrites the first.
 17. javis_web_fetch and page watching connect to the exact address the private-network check vetted (DNS
     rebinding), with the real host in the Host header and the TLS name.
"""
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-audit-low-")

from _paths import ROOT, SERVER  # noqa: E402,F401
from pathlib import Path  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


# ============================================================
# 15. chat-scope token
# ============================================================
import config  # noqa: E402

tok = config.create_api_token("t", scope="chat")
raw = tok.get("token") or tok.get("raw") or ""
check("15. a chat token was created", raw.startswith(config.TOKEN_PREFIX), tok)
for path in ("/chat", "/chat/stream", "/sessions", "/sessions/abc/messages", "/version", "/health"):
    check(f"15. chat token reaches {path}", config.verify_api_token(raw, path) is not None)
for path in ("/chatbots", "/chatbots/x/delete", "/chatbot-api/v1/turn", "/sessionsx", "/settings", "/healthz"):
    check(f"15. chat token does NOT reach {path}", config.verify_api_token(raw, path) is None)

# ============================================================
# 14. /health public as an exact path only
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

check("14. /health is an exact public path", "/health" in main._AUTH_PUBLIC_EXACT)
check("14. no public prefix without its trailing slash",
      all(p.endswith("/") for p in main._AUTH_PUBLIC_PREFIX), main._AUTH_PUBLIC_PREFIX)
main.cfgmod.gate_active = lambda: True
main.cfgmod.auth_enabled = lambda: True
cl = TestClient(main.app, base_url="http://localhost:7777")
check("14. /health still answers without login", cl.get("/health").status_code == 200)
check("14. /health/loop needs the login", cl.get("/health/loop").status_code == 401)
check("14. the dashboard's static files still load without login",
      cl.get("/static/i18n/vi.json").status_code == 200)

# ============================================================
# 16. WhatsApp file names
# ============================================================
src = Path(SERVER, "whatsapp_bot.py").read_text(encoding="utf-8")
khoi = src.split("2026-11-05 audit: the customer's file name", 1)[-1].split("dest.write_bytes(data)", 1)[0]
check("16. WhatsApp picks a free name before writing (no overwrite)",
      "while dest.exists():" in khoi and 'lstrip(".")' in khoi)

# ============================================================
# 17. Fetch pinned to the vetted address
# ============================================================
import httpx  # noqa: E402
import socket  # noqa: E402
import web_tools  # noqa: E402
import web_watch  # noqa: E402

PUBLIC, PRIVATE = "93.184.216.34", "169.254.169.254"
answers = []


def fake_getaddrinfo(host, port, *a, **kw):
    ip = answers.pop(0) if answers else PRIVATE      # rebinding: the second answer points inside
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]


web_watch.socket.getaddrinfo = fake_getaddrinfo
seen = []


def handler(req):
    seen.append((req.url.host, req.headers.get("host"), req.extensions.get("sni_hostname")))
    return httpx.Response(200, text="<html><title>T</title><p>xin chao</p></html>",
                          headers={"content-type": "text/html"})


web_tools._TRANSPORT = httpx.MockTransport(handler)
answers[:] = [PUBLIC]
cur, title, text = asyncio.run(web_tools._tai("https://rebind.example/a"))
check("17. web_fetch connects to the vetted public address, not a second lookup",
      seen and seen[-1][0] == PUBLIC, seen)
check("17. the Host header keeps the real host", seen and seen[-1][1] == "rebind.example", seen)
check("17. TLS name (SNI and certificate check) is the real host", seen and seen[-1][2] == "rebind.example", seen)
check("17. the page reads normally", "xin chao" in text and cur == "https://rebind.example/a", (cur, text))
answers[:] = [PRIVATE]
try:
    asyncio.run(web_tools._tai("https://rebind.example/b"))
    check("17. a name that resolves inside is still refused", False)
except web_tools.LoiWeb:
    check("17. a name that resolves inside is still refused", True)
check("17. nothing left behind in the vetted table for a refused URL",
      "https://rebind.example/b" not in web_watch._VETTED)
check("17. pinned(): an IP URL is left alone", web_watch.pinned("http://1.2.3.4/", PUBLIC) == ("http://1.2.3.4/", {}, {}))
u, h, e = web_watch.pinned("http://v6.example/x", "2606:2800::1")
check("17. pinned(): IPv6 is bracketed, plain http has no SNI", u == "http://[2606:2800::1]/x" and h == {"Host": "v6.example"}
      and e == {}, (u, h, e))
src_ww = Path(SERVER, "web_watch.py").read_text(encoding="utf-8")
check("17. page watching uses the same pinning", "goi, them, ext = pinned(cur, vetted_ip(cur))" in src_ww)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
