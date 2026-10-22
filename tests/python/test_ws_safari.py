"""0.197.1: Safari lost the live socket for minutes while Chrome stayed connected (customer report 17/10/2026).

    python tests/run.py ws_safari

- WebSocket compression (permessage-deflate) is never negotiated, however uvicorn is started: a real uvicorn CLI
  process with its default settings, and a client that offers compression.
- JAVIS_WS_DEFLATE=1 keeps compression for whoever needs it.
- A page that got its socket back reports how it lost it; /health/loop shows the last reports, bounded.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ═════ a real uvicorn CLI process (like the Docker image, systemd and update.sh start it) ═════
APP = '''
import ws_compat
ws_compat.disable_deflate()
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

async def echo(ws):
    await ws.accept()
    await ws.send_text("x" * 50000)
    await ws.close()

app = Starlette(routes=[WebSocketRoute("/ws", echo)])
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def negotiated(env_extra):
    d = Path(tempfile.mkdtemp(prefix="javis-ws-compat-"))
    (d / "wsapp.py").write_text(APP, encoding="utf-8")
    port = free_port()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(SERVER), str(d)]), **env_extra)
    env.pop("UVICORN_WS_PER_MESSAGE_DEFLATE", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "wsapp:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=str(d), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        async def go():
            from websockets.asyncio.client import connect
            async with connect(f"ws://127.0.0.1:{port}/ws", compression="deflate") as ws:
                ext = ws.response.headers.get("Sec-WebSocket-Extensions") or ""
                msg = await ws.recv()
                return ext, len(msg)
        return asyncio.run(go())
    finally:
        proc.terminate()
        proc.wait(timeout=10)


ext, n = negotiated({})
check("uvicorn started from the CLI with its defaults does not negotiate compression", "permessage-deflate" not in ext,
      ext)
check("a large message still arrives whole", n == 50000, n)
ext, _ = negotiated({"JAVIS_WS_DEFLATE": "1"})
check("JAVIS_WS_DEFLATE=1 keeps compression", "permessage-deflate" in ext, ext)

# 0.274.0: ws_compat no longer loads uvicorn itself; when main comes first (`python main.py`), the patch lands as soon as
# uvicorn.config loads.
LATE = ("import sys, ws_compat; ws_compat.disable_deflate(); print('uvicorn' in sys.modules); "
        "import uvicorn.config as u; print(u.Config('x:y').ws_per_message_deflate)")
late = subprocess.run([sys.executable, "-c", LATE], cwd=str(SERVER), capture_output=True, text=True,
                      env={k: v for k, v in os.environ.items() if k != "JAVIS_WS_DEFLATE"})
check("disable_deflate does not load uvicorn, and a uvicorn loaded after it still has compression off",
      late.stdout.split() == ["False", "False"], (late.stdout, late.stderr[-300:]))

main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
i_compat = main_src.find("ws_compat.disable_deflate()")
i_app = main_src.find("app = FastAPI(")
check("main.py turns compression off at import, before the app takes connections", 0 < i_compat < i_app,
      (i_compat, i_app))
check("python main.py starts uvicorn without compression too",
      "ws_per_message_deflate=ws_compat.wanted()" in main_src)

# ═════ drop reports ═════
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ws-drops-")
import main  # noqa: E402
import loop_watch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
r = c.post("/diag/ws-drops", headers=H, json={
    "ua": "Mozilla/5.0 (Macintosh) Version/18.0 Safari/605.1.15", "down_s": 612.4,
    "drops": [{"code": 1006, "clean": False, "open_s": 3.2, "at": 1760670000}, {"code": "connect_timeout"}]})
rep = c.get("/health/loop").json()
d = (rep.get("client_drops") or [{}])[0]
check("a page reports how it lost its socket", r.status_code == 200 and "Safari" in d.get("ua", "")
      and d.get("down_s") == 612.4 and [x["code"] for x in d.get("drops", [])] == ["1006", "connect_timeout"], (r.text, d))
for _ in range(40):
    loop_watch.note_client_drops({"ua": "x" * 999, "drops": [{"code": "y" * 99}] * 50, "down_s": "bad"})
rep = c.get("/health/loop").json()
check("reports are bounded: last 30, at most 10 drops each, short strings",
      len(rep["client_drops"]) == loop_watch.CLIENT_DROPS and len(rep["client_drops"][0]["drops"]) == 10
      and len(rep["client_drops"][0]["ua"]) == 200 and len(rep["client_drops"][0]["drops"][0]["code"]) == 20
      and rep["client_drops"][0]["down_s"] == 0.0)
check("a junk body is ignored, not an error", c.post("/diag/ws-drops", headers=H, json={"drops": "nope"}).status_code == 200)

app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("the page records every kind of drop (close code, silent socket, stuck handshake)",
      "_ghiDut(e && e.code" in app_js and '_ghiDut("ping"' in app_js and '_ghiDut("connect_timeout"' in app_js)
check("the page reports once it is back (on hello)", "_baoDutVeMayChu();" in app_js and '"/diag/ws-drops"' in app_js)
for name in ("server/ws_compat.py", "server/loop_watch.py"):
    s = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", "\u2014" not in s and "\u2013" not in s)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_ws_safari")
raise SystemExit(1 if fails else 0)
