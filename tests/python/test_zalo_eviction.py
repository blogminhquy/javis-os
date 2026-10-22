"""Another session evicting a Zalo connection, and replies Zalo never confirmed (0.283.0).

    python tests/run.py zalo_eviction      (no network; spawns a few sleeping dummy processes on Linux)

Field report 22/10/2026 (bot Javis Vũ): after an update, the account's live socket was evicted right after every
re-login, javis-zalo backed off up to five minutes, and the bot only heard messages in the seconds after each
reconnect. Three hours of tags went unanswered while the bot card stayed green, and some replies showed in the bot
history without ever reaching the customer. Checks:
  1. the leftover-process ledger: a live pid with a different start time is NOT the old server; a tarball URL also
     yields the package-name marker npx's node child carries;
  2. reap_same_home kills a second `... zalo ... mcp start` on the same HOME, never another HOME, a plain CLI
     command on that HOME, or the group we keep;
  3. the read-loop watch spots rapid closes in the MCP log, kills local rivals, marks the bot card, rings once;
  4. a send that javis-zalo reports as success without a message id counts as failed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import subprocess
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-evict-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_orphans  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


URL = "https://codeload.github.com/blogminhquy/javis-zalo/tar.gz/refs/tags/v1.6.1"

# ---- 1. ledger ---------------------------------------------------------------------------------------
check("markers: last long arg plus the package name of a tarball URL",
      mcp_orphans._markers(["-y", "--prefer-offline", URL, "mcp", "start"]) == [URL, "/javis-zalo/"])
check("markers: an ordinary package keeps one marker", mcp_orphans._markers(["-y", "mcp-server-gsc"]) == ["mcp-server-gsc"])
LINUX = os.name != "nt" and os.path.isdir("/proc")
if LINUX:
    me = os.getppid()       # alive, and not us
    check("owner alive: same pid, same start time", mcp_orphans.owner_alive(
        {"server_pid": me, "server_start": mcp_orphans._proc_start(me)}))
    check("owner NOT alive: the pid now belongs to a process that started at another time",
          not mcp_orphans.owner_alive({"server_pid": me, "server_start": "1"}))
    check("owner alive when the record has no start time (older ledger)", mcp_orphans.owner_alive({"server_pid": me}))
check("owner NOT alive: our own pid", not mcp_orphans.owner_alive({"server_pid": os.getpid()}))

sess = mcp_client.McpStdioSession("npx", ["-y", URL, "mcp", "start"], env={"HOME": "/tmp/zl"}, key="zl-1")
check("Zalo mcp start is a single-socket session", sess.single_socket_home() == "/tmp/zl")
check("other servers are not", mcp_client.McpStdioSession("npx", ["-y", "mcp-server-gsc"], env={"HOME": "/tmp/x"},
                                                          key="g").single_socket_home() == "")
check("a Zalo CLI command is not", mcp_client.McpStdioSession("npx", ["-y", URL, "msg", "send"], env={"HOME": "/tmp/zl"},
                                                              key="z").single_socket_home() == "")

# ---- 2. reap_same_home on real processes ------------------------------------------------------------------
if LINUX:
    home_a, home_b = tempfile.mkdtemp(prefix="zl-a-"), tempfile.mkdtemp(prefix="zl-b-")

    def dummy(home, *words):
        env = dict(os.environ, HOME=home)
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "javis-zalo", *words],
                                env=env, start_new_session=True)

    rival = dummy(home_a, "mcp", "start")
    keep = dummy(home_a, "mcp", "start")
    other_home = dummy(home_b, "mcp", "start")
    cli = dummy(home_a, "msg", "send-image")
    time.sleep(0.3)
    killed = mcp_orphans.reap_same_home(home_a, keep_pgids=(keep.pid,))
    time.sleep(0.3)
    check("the rival on the same HOME is killed", rival.poll() is not None and rival.pid in killed, (killed, rival.poll()))
    check("the kept group survives", keep.poll() is None)
    check("another HOME survives", other_home.poll() is None)
    check("a plain CLI command on the same HOME survives", cli.poll() is None)
    for p in (keep, other_home, cli):
        p.kill()
        p.wait()
    check("no HOME given: nothing killed", mcp_orphans.reap_same_home("") == [])
else:
    print("skip reap_same_home (no /proc)")

# ---- 3. read-loop watch ------------------------------------------------------------------------------------
check("thrash_of reads the latest close line",
      zc.thrash_of(["x", "[mcp] Connection closed (code: 1000). Re-login in 300s... (reconnect #7, rapid #4)", "y"])
      == (7, 4))
check("thrash_of: none", zc.thrash_of(["[mcp] Reconnected (#2)"]) is None)

STATE = {"lines": [], "pid": 4242}
REAPED, BELL = [], []
mcp_client.pool.session_pid = lambda key: STATE["pid"]
mcp_client.pool.stderr_lines = lambda key: list(STATE["lines"])
mcp_orphans.reap_same_home = lambda home, keep_pgids=(): REAPED.append((home, tuple(keep_pgids))) or [99]


async def _bell(*a, **k):
    BELL.append(a[1] if len(a) > 1 else k)


zc.NOTIFY_OWNER = _bell
CONN = {"id": "zl-1", "label": "Javis Vũ", "env": {"HOME": "/tmp/zl"}}


async def watch(lines):
    STATE["lines"] = lines
    zc._soi_tranh_phien(CONN)
    await asyncio.sleep(0)


def line(n, k):
    return f"[mcp] Connection closed (code: 1000). Re-login in 300s... (reconnect #{n}, rapid #{k})"


asyncio.run(watch([line(1, 1)]))
check("one quick close is not a rival", not REAPED and not BELL and not zc.evicted_recently("zl-1"))
asyncio.run(watch([line(1, 1), line(2, 3)]))
check("rapid closes: local rivals reaped, keeping our own group", REAPED == [("/tmp/zl", (4242,))], REAPED)
check("rapid closes: the bot card shows eviction", zc.evicted_recently("zl-1"))
check("rapid closes: the owner is told once", len(BELL) == 1 and "Javis Vũ" in str(BELL[0]), BELL)
asyncio.run(watch([line(1, 1), line(2, 3)]))
check("the same log line is handled once", len(REAPED) == 1 and len(BELL) == 1)
asyncio.run(watch([line(3, 4)]))
check("a new rapid close reaps again but does not ring again within the gap", len(REAPED) == 2 and len(BELL) == 1)
STATE["pid"] = 5555
asyncio.run(watch([line(1, 3)]))
check("a new MCP process with its own counters is watched again", len(REAPED) == 3)

# ---- 4. unconfirmed send --------------------------------------------------------------------------------------
REPLY = {"v": {"success": True, "messageId": None}}


async def _goi(conn, tool, args):
    return REPLY["v"]


zc._goi = _goi
ok, err = asyncio.run(zp._gui_mot({"id": "zl-1"}, "u1", "Dạ", "private"))
check("success without a message id counts as failed", ok is False and err, (ok, err))
REPLY["v"] = {"success": True, "messageId": "123"}
check("success with a message id is sent", asyncio.run(zp._gui_mot({"id": "zl-1"}, "u1", "Dạ", "private"))[0] is True)
REPLY["v"] = {"success": True}
check("an MCP that does not report ids at all is trusted as before",
      asyncio.run(zp._gui_mot({"id": "zl-1"}, "u1", "Dạ", "private"))[0] is True)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
