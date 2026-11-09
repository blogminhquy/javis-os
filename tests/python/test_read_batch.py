"""Batched reads (2026-11-08, performance stage 2): POST /batch runs many dashboard reads in one round trip.

Owner, 2026-11-08: pages and chat switches took seconds over the Cloudflare tunnel. Each moment of the app made its
reads in 3 to 5 waves; the dashboard now learns them and sends them together (dashboard/fetch-gop.js), and this
route runs them through the app itself and streams each answer back as it finishes.

  1. Only plain reads run: side-effect GETs, explicit refreshes, unknown paths, /batch itself are left out; at most 40.
  2. The server list and the dashboard list (BATCH_RE in fetch-gop.js) accept the same paths.
  3. The route answers each allowed read with exactly what a direct GET answers, as server-sent events.
  4. It goes through the auth guard like any other route: no session, no answers.
  5. A read that never finishes is cut at SUB_TIMEOUT_S and the stream ends (httpx's own timeout does nothing over
     ASGITransport; customer report 2026-11-08: the Partners chat box stayed locked after the update).
  6. Behind a reverse proxy, a batched read sees the same X-Forwarded-Proto/Host as a direct GET: /messenger/setup
     answers https, so the Facebook sign-in button is not locked (#1226). X-Forwarded-For is not passed on.

    python tests/run.py read_batch
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-read-batch-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import read_batch  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. what may run ----------------------------------------------------------------------------------------------------
ok_paths = ["/settings", "/skills?brain=brain", "/sessions/3292f379b17b41ffa56591518c3b4e85?limit=30&tools=0",
            "/sessions/3292f379b17b41ffa56591518c3b4e85/meta", "/background?brain=brain&chat_id=web%3Aabc",
            "/telegram/status", "/agents/javis-core/pulse?brain=brain", "/usage/summary?period=this_month&refresh=0"]
for p in ok_paths:
    check(f"a plain read may run: {p}", read_batch.allowed(p))
bad_paths = ["/workflows/run?slug=x", "/workflows/resume", "/claude/status?refresh=1", "/usage/summary?refresh=true",
             "/batch", "/static/app.js", "/files/raw?path=x", "/files/read?path=x", "/sessions/../settings",
             "settings", "/sessions/search?q=x", "/hub/mcp", "/settings#x", "/" + "a" * 700, None, 5]
for p in bad_paths:
    check(f"left out: {str(p)[:40]}", not read_batch.allowed(p))
many = ["/settings"] * 3 + [f"/sessions/{i:032x}" for i in range(60)]
cleaned = read_batch.clean_paths(many)
check("duplicates go and at most 40 paths are read", cleaned.count("/settings") == 1 and len(cleaned) <= read_batch.BATCH_MAX)
check("a body that is not a list reads nothing", read_batch.clean_paths("x") == [] and read_batch.clean_paths(None) == [])

# ---- 2. same list on both sides ---------------------------------------------------------------------------------------------
def samples(pattern):
    """Concrete paths for one ALLOWED_PATHS entry: each group alternative, wildcards filled in."""
    m = re.search(r"\(([^()]*)\)", pattern)
    if m:
        out = []
        for alt in m.group(1).split("|"):
            out += samples(pattern[:m.start()] + alt + pattern[m.end():])
        return out
    return ["/" + pattern.replace("[^/?]+", "javis-core").replace("[0-9a-z]{8,64}", "3292f379b17b41ff")]


corpus = []
for pat in read_batch.ALLOWED_PATHS:
    for p in samples(pat):
        corpus += [p, p + "?brain=brain"]
corpus += [p for p in bad_paths if isinstance(p, str)] + ["/version", "/provider/models?provider=x", "/chat/suggest"]
# The dashboard normalises a path the way the browser will send it ("/a/../b" is "/b"), so compare on what it returns.
js = ("const g=require(process.argv[1]);const ps=JSON.parse(process.argv[2]);"
      "console.log(JSON.stringify(ps.map(p=>g.batchPath(p,undefined,'https://j.x'))));")
out = subprocess.run(["node", "-e", js, str(ROOT / "dashboard" / "fetch-gop.js"), json.dumps(corpus)],
                     capture_output=True, text=True, encoding="utf-8")
try:
    js_ok = json.loads(out.stdout.strip())
except Exception:
    js_ok = []
diff = [p for p, j in zip(corpus, js_ok) if bool(j) != read_batch.allowed(j or p)]
check("the dashboard batches exactly the reads the server runs", len(js_ok) == len(corpus) and not diff,
      diff or out.stderr[-300:])

# ---- 3. the route ---------------------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import config as cfgmod  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)


def events(text):
    out = {}
    for ev in text.split("\n\n"):
        if ev.startswith("data: "):
            d = json.loads(ev[6:])
            out[d["p"]] = d
    return out


want = ["/settings", "/brains", "/config", "/workflows/run?slug=x", "/claude/status?refresh=1"]
r = client.post("/batch", json={"paths": want})
got = events(r.text)
check("the route streams server-sent events", r.status_code == 200 and r.headers.get("content-type", "").startswith("text/event-stream"), r.headers)
check("every allowed read is answered", set(got) == {"/settings", "/brains", "/config"}, list(got))
same = all(got[p]["s"] == 200 and json.loads(got[p]["b"]) == client.get(p).json() for p in got)
check("each answer is exactly what a direct GET answers", same)
check("its content type comes along", all(got[p]["t"].startswith("application/json") for p in got))
check("a body that is not JSON is refused", client.post("/batch", content=b"x", headers={"content-type": "application/json"}).status_code == 400)
check("nothing allowed: an empty stream", client.post("/batch", json={"paths": ["/workflows/run"]}).text == "")

# ---- 4. the auth guard ----------------------------------------------------------------------------------------------------
real = cfgmod.gate_active
cfgmod.gate_active = lambda: True
try:
    r = client.post("/batch", json={"paths": ["/settings"]})
    check("without a session the batch is refused like any route", r.status_code == 401 and "workspace_name" not in r.text, r.status_code)
finally:
    cfgmod.gate_active = real

# ---- 5. a read that never finishes ----------------------------------------------------------------------------------------
import asyncio  # noqa: E402
import time  # noqa: E402


async def _never_ends():
    await asyncio.sleep(3600)
    return {}

main.app.add_api_route("/batch-test-hang", _never_ends, methods=["GET"])
real_allowed, real_timeout = read_batch._ALLOWED, read_batch.SUB_TIMEOUT_S
read_batch._ALLOWED = re.compile(r"^/(settings|batch-test-hang)(\?[^#]*)?$")
read_batch.SUB_TIMEOUT_S = 0.5
try:
    t0 = time.monotonic()
    r = client.post("/batch", json={"paths": ["/settings", "/batch-test-hang"]})
    took = time.monotonic() - t0
    got = events(r.text)
    check("a read that never finishes is cut and the stream ends", took < 5, round(took, 1))
    check("the quick read is still answered, the stuck one is left out", set(got) == {"/settings"}, list(got))
finally:
    read_batch._ALLOWED, read_batch.SUB_TIMEOUT_S = real_allowed, real_timeout
check("the cut is a real wait_for, not httpx's timeout", "asyncio.wait_for(sub.get(p), SUB_TIMEOUT_S)"
      in (ROOT / "server" / "read_batch.py").read_text(encoding="utf-8"))

# ---- 6. behind a reverse proxy ---------------------------------------------------------------------------------------------
proxy = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "javis.example.com"}
direct = client.get("/messenger/setup?brain=brain", headers=proxy).json()
r = client.post("/batch", json={"paths": ["/messenger/setup?brain=brain", "/threads/setup?brain=brain"]}, headers=proxy)
got = events(r.text)
ms = json.loads(got.get("/messenger/setup?brain=brain", {}).get("b") or "{}")
th = json.loads(got.get("/threads/setup?brain=brain", {}).get("b") or "{}")
check("a direct GET behind the proxy answers https", direct.get("https") is True, direct.get("webhook_url"))
check("the batched /messenger/setup answers https too", ms.get("https") is True, ms.get("webhook_url"))
check("its webhook address is the public one", str(ms.get("webhook_url") or "").startswith("https://javis.example.com/"),
      ms.get("webhook_url"))
check("the batched answer equals the direct one", ms == direct)
check("the batched /threads/setup builds https addresses",
      "http://" not in json.dumps(th) and "https://javis.example.com" in json.dumps(th), th)
check("X-Forwarded-For is still not passed on", "x-forwarded-for" not in read_batch._FORWARD)

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("the route is registered at the end of main.py", src.rstrip().endswith("return await read_batch.handle(app, request)"))
for name in ("server/read_batch.py", "tests/python/test_read_batch.py"):
    s = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_read_batch")
raise SystemExit(1 if fails else 0)
