"""GET /domain/status must never freeze the server (owner report 25/10/2026).

    python tests/run.py domain_status_loop      (no network: the lookups are stubbed with slow fakes)

"Bị mất kết nối khi 1 người khác truy cập vào javis ở máy khác": every dashboard load asks /domain/status
(branding.js loadExtras), and the route looked up the server's public IP (three HTTPS services, DNS + 4s timeout
each, not cached when they failed) and resolved the saved domain ON THE EVENT LOOP. On a server whose DNS or outbound
HTTPS is slow, one visitor opening Javis froze the whole server for 12 to 24 seconds (measured with Playwright: the
other open page's ping went unanswered past its 20s wait and it dropped with code "ping"). This file pins:

1. while /domain/status waits on slow lookups, the event loop keeps running (other pages get their pong);
2. a failed public IP lookup is remembered for a while, so the next visitors do not pay for it again;
3. pages opened together share one lookup.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-domain-loop-test-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
os.environ.pop("JAVIS_DEPLOY_TARGET", None)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx                                  # noqa: E402
import config as c                            # noqa: E402
import main                                   # noqa: E402
import routes.domain as dom                   # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


SLOW = 0.4          # seconds each fake lookup takes; the old code ran 3 of them plus the DNS one on the loop
calls = {"urlopen": 0, "dns": 0}
_lock = threading.Lock()


def slow_urlopen(url, timeout=None, **kw):
    with _lock:
        calls["urlopen"] += 1
    time.sleep(SLOW)
    raise OSError("network unreachable (test)")


def slow_gethostbyname(name):
    with _lock:
        calls["dns"] += 1
    time.sleep(SLOW)
    return "203.0.113.7"


async def probe_ok(domain, hostinger=False):
    return False, "test", "unreachable"


urllib.request.urlopen = slow_urlopen
socket.gethostbyname = slow_gethostbyname
dom._probe_https = probe_ok
c.update_settings({"domain": {"custom": "javis.example.com"}})


async def run(n_requests):
    """Ask /domain/status n times at once while a ticker measures the longest gap between event-loop turns."""
    gaps = []
    stop = asyncio.Event()

    async def ticker():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.02)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    t = asyncio.create_task(ticker())
    transport = httpx.ASGITransport(app=main.app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7777") as cl:
        rs = await asyncio.gather(*[cl.get("/domain/status") for _ in range(n_requests)])
    stop.set()
    await t
    return rs, max(gaps or [0.0])


dom._PUBLIC_IP_CACHE.update(ip=None, ts=0.0, miss_ts=0.0)
rs, worst = asyncio.run(run(1))
body = rs[0].json()
check("/domain/status answers while the lookups fail", rs[0].status_code == 200 and body.get("server_ip") is None,
      rs[0].text[:200])
check("the saved domain is still resolved", body.get("dns_ip") == "203.0.113.7", body)
check(f"the event loop keeps turning during slow lookups (longest stall {worst:.2f}s, lookups take "
      f"{SLOW * 3 + SLOW:.1f}s)", worst < SLOW, f"{worst:.2f}s")

# 2. A failed lookup is not repeated by the next visitor.
before = calls["urlopen"]
rs, worst = asyncio.run(run(1))
check("the next visitor does not repeat a lookup that just failed", calls["urlopen"] == before,
      f"{calls['urlopen'] - before} more requests")

# 3. Pages opened together share one lookup.
dom._PUBLIC_IP_CACHE.update(ip=None, ts=0.0, miss_ts=0.0)
before = calls["urlopen"]
rs, worst = asyncio.run(run(3))
check("three pages opened together cost one round of lookups (3 services)", calls["urlopen"] - before == 3,
      f"{calls['urlopen'] - before} requests")
check("and none of them stalls the loop", worst < SLOW, f"{worst:.2f}s")

# A found address is still cached the usual way.
dom._PUBLIC_IP_CACHE.update(ip="198.51.100.4", ts=time.time(), miss_ts=0.0)
before = calls["urlopen"]
rs, worst = asyncio.run(run(1))
check("a found address is served from the cache", rs[0].json().get("server_ip") == "198.51.100.4"
      and calls["urlopen"] == before, rs[0].text[:200])

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_domain_status_loop: all pass")
