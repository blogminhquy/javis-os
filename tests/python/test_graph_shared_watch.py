"""One OS file watcher per folder, shared by every graph socket (2026-11-09).

    python tests/run.py graph_shared_watch      (no network)

The owner's /health/loop after 0.521.1 still showed graph.py _fs_watcher 4 times, up to 2.74 s: watchfiles builds its
RustNotify while holding the GIL, so building it on its own thread still froze the event loop, and every graph tab and
every reconnect built a new one. Now the first socket builds the watcher, later ones join it, and it lingers after the
last one leaves. Checks: two sockets share one build and both get the event, a socket that comes back after everyone
left joins the lingering watcher without a rebuild, the watcher stops once the linger time runs out, and nested roots
are watched once.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import queue
import sys
import tempfile
import threading
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sharedwatch-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


import main  # noqa: E402
from routes import graph as graph_routes  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
import watchfiles  # noqa: E402

# ---- nested roots are watched once ----
base = tempfile.mkdtemp(prefix="javis-sharedwatch-roots-")
inner = os.path.join(base, "inner")
sibling = base + " b"
os.makedirs(inner)
os.makedirs(sibling)
got = graph_routes._watch_roots([inner, base, sibling, os.path.join(base, "missing"), "", None, base + os.sep])
check("a root inside another root is dropped, a sibling with the same prefix is kept, missing ones are skipped",
      got == [os.path.normpath(base), os.path.normpath(sibling)], got)

# ---- sockets share one watcher ----
root = tempfile.mkdtemp(prefix="javis-sharedwatch-vault-")
builds = []
events = queue.Queue()
stopped = threading.Event()


def fake_watch(*paths, stop_event=None, watch_filter=None, **kw):
    """Stands in for watchfiles.watch: counts builds, reports each note put on `events`, ends on stop_event."""
    builds.append(paths)
    try:
        while not stop_event.is_set():
            try:
                note = events.get(timeout=0.05)
            except queue.Empty:
                continue
            yield {(watchfiles.Change.added, note)}
    finally:
        stopped.set()


watchfiles.watch = fake_watch
main.cfgmod.gate_active = lambda: False
client = TestClient(main.app)


def recv(ws, timeout=10):
    out = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: out.put(ws.receive_text()), daemon=True).start()
    return json.loads(out.get(timeout=timeout))


def write(name):
    p = os.path.join(root, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("note " + name)
    return p


url = f"/ws/graph?path={root}"
hdr = {"host": "127.0.0.1"}
with client.websocket_connect(url, headers=hdr) as ws1:
    with client.websocket_connect(url, headers=hdr) as ws2:
        time.sleep(0.3)
        check("two graph sockets on one folder build ONE watcher", len(builds) == 1, len(builds))
        events.put(write("first.md"))
        a, b = recv(ws1), recv(ws2)
        check("both sockets get the change", a.get("node", {}).get("id") == "first"
              and b.get("node", {}).get("id") == "first", (a, b))
time.sleep(0.3)
check("the watcher keeps running after the last socket leaves (lingers)", not stopped.is_set()
      and os.path.normpath(root) in graph_routes._shared_watches)

with client.websocket_connect(url, headers=hdr) as ws3:
    time.sleep(0.3)
    check("a socket that comes back joins the lingering watcher, no rebuild", len(builds) == 1, len(builds))
    events.put(write("second.md"))
    c = recv(ws3)
    check("the socket that came back gets changes", c.get("node", {}).get("id") == "second", c)
    graph_routes._WATCH_LINGER_S = 0
for _ in range(60):
    if stopped.is_set():
        break
    time.sleep(0.05)
check("once the linger time runs out the watcher stops", stopped.is_set())
time.sleep(0.2)
check("a stopped watcher leaves the shared table", os.path.normpath(root) not in graph_routes._shared_watches,
      list(graph_routes._shared_watches))

graph_routes._WATCH_LINGER_S = 900
with client.websocket_connect(url, headers=hdr) as ws4:
    time.sleep(0.3)
    check("after it stopped, the next socket builds a fresh watcher", len(builds) == 2, len(builds))
    events.put(write("third.md"))
    d = recv(ws4)
    check("the fresh watcher delivers changes", d.get("node", {}).get("id") == "third", d)

src = (ROOT / "server" / "routes" / "graph.py").read_text(encoding="utf-8")
check("ws_graph no longer builds a watcher per socket", "_watch_join(roots, loop, queue)" in src
      and "watch(*live" not in src and "async def _fs_watcher" not in src)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + ", ".join(_fails))
else:
    print("OK - test_graph_shared_watch: all pass")
sys.stdout.flush()
sys.stderr.flush()
import _paths  # noqa: E402  - os._exit skips atexit, so clean the temp folders first
_paths.don_thu_muc_tam()
os._exit(1 if _fails else 0)
