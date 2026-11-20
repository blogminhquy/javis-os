"""Two personal Zalo accounts on one Javis: signing in the second must not cut the first off.

    python tests/run.py zalo_two_accounts      (no network; spawns a few sleeping dummy processes)

Field reports 19-20/11/2026: two Zalo accounts, one bot each in two brains. Right after the second account was signed
in, the first bot's card read "another session of this account keeps taking the Zalo connection" and stayed that way.
The QR sign-in saves its connection from a worker thread, `mcp_hub.invalidate_cache` dropped every MCP session from
there, and `SessionPool._close_later` did nothing without a running loop: the first account's javis-zalo kept running
outside the pool while the read loop started a second one on the same HOME. Checks:
  1. a session dropped from a worker thread is closed on the loop that runs it;
  2. with no loop known, its process tree is killed right away;
  3. invalidate_cache leaves an unchanged single-socket session (Zalo) running, still restarts the others;
  4. scanning the QR with an account that is already connected adds no second connection.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo2-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import zalo_login  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


class FakeStdio:
    """Stands in for McpStdioSession: a real child process, the same close and kill methods."""

    def __init__(self):
        self.proc = _sleeper()
        self.closed_in = None

    def _kill_tree(self):
        self.proc.kill()

    async def close(self):
        self.closed_in = threading.get_ident()
        self._kill_tree()


def _dead(p, wait=3.0):
    try:
        p.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        return False
    return True


def _from_thread(fn):
    t = threading.Thread(target=fn)
    t.start()
    t.join()


# ---- 1 + 2. closing from a worker thread ------------------------------------------------------------
async def _thread_drop():
    pool = mcp_client.SessionPool()
    pool._get({"key": "warm", "transport": "http", "url": "http://127.0.0.1:9"})      # the pool learns its loop
    fake = FakeStdio()
    pool._sessions["z1"] = {"obj": fake, "hash": 1, "last": 0.0 + __import__("time").time()}
    _from_thread(lambda: pool.invalidate("z1", defer_if_starting=True))
    check("thread drop: the session left the pool", "z1" not in pool._sessions)
    for _ in range(40):
        if fake.closed_in:
            break
        await asyncio.sleep(0.05)
    check("thread drop: closed on the loop that runs the sessions", fake.closed_in == threading.get_ident(),
          fake.closed_in)
    check("thread drop: its process is gone", _dead(fake.proc))


asyncio.run(_thread_drop())

pool = mcp_client.SessionPool()
fake = FakeStdio()
pool._sessions["z1"] = {"obj": fake, "hash": 1, "last": __import__("time").time()}
_from_thread(lambda: pool.invalidate("z1"))
check("no loop known: the process tree is killed right away", _dead(fake.proc))

# ---- 3. invalidate_cache spares an unchanged Zalo session ---------------------------------------------
ZALO_CON = {"id": "zalo", "isolate_home": True}
conns = [
    {"id": "z1", "connector_id": "zalo", "transport": "stdio", "command": "npx", "args": ["mcp", "start"],
     "env": {"HOME": "/tmp/z1"}, "connector": ZALO_CON, "label": "Zalo 1"},
    {"id": "z2", "connector_id": "zalo", "transport": "stdio", "command": "npx", "args": ["mcp", "start"],
     "env": {"HOME": "/tmp/z2"}, "connector": ZALO_CON, "label": "Zalo 2"},
    {"id": "gs", "connector_id": "sheets", "transport": "stdio", "command": "uvx", "args": ["gs"],
     "env": {}, "connector": {"id": "sheets"}, "label": "Sheets"},
]
real_resolved, real_list = mcp_store.resolved, mcp_store.list_connections
mcp_store.resolved = lambda enabled_only=True: conns
mcp_store.list_connections = lambda *a, **k: [{"id": c["id"]} for c in conns] + [{"id": "off"}]
real_pool = mcp_client.pool
mcp_client.pool = pool = mcp_client.SessionPool()
fakes = {}
try:
    for c in conns:
        fakes[c["id"]] = FakeStdio()
        h = mcp_client._spec_hash(mcp_client._conn_spec(c))
        if c["id"] == "z2":
            h += 1                                  # z2's session was started with an older spec
        pool._sessions[c["id"]] = {"obj": fakes[c["id"]], "hash": h, "last": __import__("time").time()}
    fakes["off"] = FakeStdio()
    pool._sessions["off"] = {"obj": fakes["off"], "hash": 5, "last": __import__("time").time()}
    _from_thread(mcp_hub.invalidate_cache)
    check("invalidate_cache: the unchanged Zalo session keeps running",
          "z1" in pool._sessions and fakes["z1"].proc.poll() is None)
    check("invalidate_cache: a Zalo session started with another spec is restarted", "z2" not in pool._sessions
          and _dead(fakes["z2"].proc))
    check("invalidate_cache: other connectors are restarted as before", "gs" not in pool._sessions
          and _dead(fakes["gs"].proc))
    check("invalidate_cache: a disabled connection's session is closed", "off" not in pool._sessions
          and _dead(fakes["off"].proc))
finally:
    for f in fakes.values():
        if f.proc.poll() is None:
            f.proc.kill()
    mcp_client.pool = real_pool
    mcp_store.resolved, mcp_store.list_connections = real_resolved, real_list

# ---- 4. the same account scanned twice ----------------------------------------------------------------
base = tempfile.mkdtemp(prefix="zalo-homes-")
h1, h2, h3 = (os.path.join(base, n) for n in ("one", "two", "three"))
os.makedirs(os.path.join(h1, ".zalo-agent-cli", "credentials"))
with open(os.path.join(h1, ".zalo-agent-cli", "accounts.json"), "w", encoding="utf-8") as f:
    json.dump([{"ownId": "111", "name": "Shop A", "active": True}], f)
os.makedirs(os.path.join(h2, ".zalo-agent-cli", "credentials"))
open(os.path.join(h2, ".zalo-agent-cli", "credentials", "cred_111.json"), "w").close()
os.makedirs(os.path.join(h3, ".zalo-agent-cli", "credentials"))
open(os.path.join(h3, ".zalo-agent-cli", "credentials", "cred_222.json"), "w").close()
check("account ids: read from the registry", zalo_login.account_ids(h1) == {"111"})
check("account ids: read from credential files", zalo_login.account_ids(h2) == {"111"})
check("account ids: an empty folder has none", zalo_login.account_ids(os.path.join(base, "none")) == set())

saved = []
real_add = mcp_store.add_connection
mcp_store.resolved = lambda enabled_only=True: [
    {"id": "c1", "connector_id": "zalo", "label": "Shop A", "env": {"HOME": h1}}]
mcp_store.add_connection = lambda cid, data: (saved.append(data) or ("new", None))
try:
    sess = {"home": h2, "label": "", "state": "qr"}
    zalo_login._finish_ok(sess, {"event": "login_success", "ownId": "111", "name": "Shop A"})
    check("same account: no second connection", saved == [], saved)
    check("same account: the sign-in ends with an error naming the connection",
          sess["state"] == "error" and "Shop A" in sess["error"] and sess.get("duplicate"), sess)
    sess = {"home": h2, "label": "", "state": "qr"}
    zalo_login._finish_ok(sess, {})
    check("same account found from the new folder when the CLI printed no id", saved == [] and sess.get("duplicate"))
    sess = {"home": h3, "label": "", "state": "qr"}
    zalo_login._finish_ok(sess, {"event": "login_success", "ownId": "222", "name": "Shop B"})
    check("another account: the connection is added", sess["state"] == "done" and len(saved) == 1
          and saved[0]["config"]["home_dir"] == h3, (sess, saved))
finally:
    mcp_store.resolved, mcp_store.add_connection = real_resolved, real_add

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
