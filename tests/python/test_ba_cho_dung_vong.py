"""2026-11-09: the three spots /health/loop still showed freezing the event loop, moved off it.

    python tests/run.py ba_cho_dung_vong      (KHÔNG mạng)

Owner: "ok em làm luôn PR sửa 3 chỗ đứng còn lại đi". From the owner's /health/loop report:
- graph.py `_fs_watcher`, 3 times, 3.08 s: awatch built its RustNotify (one OS watch per folder) on the loop each time
  the graph screen opened. Now the sync `watch` builds and waits on its own thread and hands batches to the loop.
- main.py `_load_community_announcements`, 1.82 s: httpx 0.27 builds a new SSL context (the whole certifi bundle) for
  every client, on the thread that creates it. Now every default client shares one context (ssl_shared.py), built on a
  worker thread at start-up.
- zalo_personal_channel `_parse_lines < watch_history < _history_turn`, 1.19 s: the history file read and parsed on the
  loop after each Zalo read. Now on a worker thread (checked in test_zalo_history_catch_up.py).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import queue
import sys
import tempfile
import threading
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bachodung-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Shared SSL context ----
import httpx  # noqa: E402
import ssl_shared  # noqa: E402

check("ssl_shared cài được vào httpx đang dùng", ssl_shared.install())
a, b, c = httpx.AsyncClient(), httpx.AsyncClient(timeout=8), httpx.Client()
ctx = a._transport._pool._ssl_context
check("mọi client mặc định dùng chung MỘT bối cảnh SSL",
      ctx is b._transport._pool._ssl_context and ctx is c._transport._pool._ssl_context)
d = httpx.AsyncClient(verify=False)
check("verify=False vẫn đi đường riêng, không dùng chung bối cảnh kiểm chứng chỉ",
      d._transport._pool._ssl_context is not ctx and d._transport._pool._ssl_context.verify_mode == 0)
check("bối cảnh chung vẫn kiểm chứng chỉ", ctx.verify_mode == 2 and ctx.check_hostname)
h2 = httpx.AsyncClient(http2=True) if __import__("importlib").util.find_spec("h2") else None
if h2 is not None:
    check("http2 có bối cảnh riêng của nó", h2._transport._pool._ssl_context is not ctx)
t0 = time.time()
for _ in range(20):
    httpx.AsyncClient()
check("tạo 20 client không dựng lại bối cảnh SSL (dưới 0,5 giây)", time.time() - t0 < 0.5, round(time.time() - t0, 3))
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("main.py cài ssl_shared ngay khi nạp và dựng sẵn trên luồng nền lúc khởi động",
      "ssl_shared.install()" in src and "await asyncio.to_thread(ssl_shared.warm)" in src)

# ---- 2. Graph watcher on its own thread ----
import main  # noqa: E402
from routes import graph as graph_routes  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
import watchfiles  # noqa: E402

gsrc = (ROOT / "server" / "routes" / "graph.py").read_text(encoding="utf-8")
check("graph.py không còn awatch (RustNotify dựng trên event loop)", "awatch(" not in gsrc)

seen = {}
root = tempfile.mkdtemp(prefix="javis-bachodung-vault-")
note = os.path.join(root, "moi.md")


def fake_watch(*paths, stop_event=None, watch_filter=None, **kw):
    """Stands in for watchfiles.watch: slow to start (a big brain), then reports one new note."""
    seen["thread"] = threading.current_thread().name
    time.sleep(0.8)
    with open(note, "w", encoding="utf-8") as f:
        f.write("note mới")
    yield {(watchfiles.Change.added, note)}
    while not stop_event.is_set():
        time.sleep(0.05)
    seen["stopped"] = True


watchfiles.watch = fake_watch
# The watcher is shared and lingers after its last socket (test_graph_shared_watch.py); 0 here so closing the
# screen still stops it, as checked below.
graph_routes._WATCH_LINGER_S = 0
main.cfgmod.gate_active = lambda: False
client = TestClient(main.app)


def recv(ws, timeout=10):
    out = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: out.put(ws.receive_text()), daemon=True).start()
    return json.loads(out.get(timeout=timeout))


with client.websocket_connect(f"/ws/graph?path={root}", headers={"host": "127.0.0.1"}) as ws:
    t0 = time.time()
    r = client.get("/brains")
    check("trong lúc bộ theo dõi đang dựng, server vẫn trả lời ngay", r.status_code == 200 and time.time() - t0 < 0.6,
          (r.status_code, round(time.time() - t0, 3)))
    msg = recv(ws)
    check("sự kiện từ luồng theo dõi tới được trình duyệt", msg.get("type") == "graph_add"
          and msg.get("node", {}).get("id") == "moi", msg)
check("bộ theo dõi chạy trên luồng riêng của nó", seen.get("thread") == "ws-graph-watch", seen)
for _ in range(60):
    if seen.get("stopped"):
        break
    time.sleep(0.05)
check("đóng màn đồ thị thì luồng theo dõi dừng", seen.get("stopped") is True)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.stdout.flush()
    os._exit(1)
print("\nOK - test_ba_cho_dung_vong: all pass")
sys.stdout.flush()
os._exit(0)
