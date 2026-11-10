"""Personal Zalo: Javis reads an account when javis-zalo says a message arrived, not on a timer (2026-11-10).

    python tests/run.py zalo_live_push      (no network, fake MCP)

Owner, 10/11/2026: "when a message arrives, send it over; do not scan on a timer, some days there is no message at
all." javis-zalo 1.10.0 POSTs a wake-up to /zalo/push; the read loop reads at once on a wake-up and makes no call to
javis-zalo for an account that pushes and has nothing pending.

Contract:
  1. zalo_push: the two variables per connection, the per-process token, `active` only for the live MCP session.
  2. Read loop: an account that does not push is read every tick, exactly as before.
  3. A pushing account with nothing pending is NOT read, and the loop does not tick at all: it sleeps until woken.
     It ticks only while a turn is on hold (released by time), and stops once that turn is released.
  4. A wake-up is read at once (well inside one tick), and a wake-up that lands during a read causes one more read.
  5. A pushing account whose process ended is read at once (the exit listener wakes the loop; that read restarts
     javis-zalo). A bot taking or leaving its post and a saved connection wake the loop too.
  6. /zalo/push: local requests with this process's bearer only; an unknown connection records nothing.
  7. `JAVIS_ZALO_PUSH=0` turns everything off.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpush-")
os.environ.pop("JAVIS_ZALO_PUSH", None)
os.environ["JAVIS_PORT"] = "7791"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_store  # noqa: E402
import zalo_push  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# ---- 1. zalo_push --------------------------------------------------------------------------------------------
env = zalo_push.env_for("zalo 1/a")
check("the URL points at this machine and names the connection (escaped)",
      env.get("JAVIS_ZALO_PUSH_URL") == "http://127.0.0.1:7791/zalo/push?conn=zalo%201%2Fa", env)
check("the token is long and the same on every call (the session identity must not change)",
      len(env.get("JAVIS_ZALO_PUSH_TOKEN", "")) >= 32 and zalo_push.env_for("zalo 1/a") == env)
check("no connection id, no variables", zalo_push.env_for("") == {})
tok = env["JAVIS_ZALO_PUSH_TOKEN"]
check("the bearer of this process is accepted", zalo_push.token_ok("Bearer " + tok) and zalo_push.token_ok("bearer " + tok))
check("a wrong, empty or bare token is refused",
      not zalo_push.token_ok("Bearer nope") and not zalo_push.token_ok("") and not zalo_push.token_ok(tok))

zalo_push.forget()
check("nothing known: not active, nothing pending", not zalo_push.active("c1", 5) and not zalo_push.pending("c1")
      and not zalo_push.take("c1"))
st = zalo_push.note("c1", {"events": ["ready", "bogus"], "version": "1.10.0", "connected": True}, epoch=5)
check("a wake-up is recorded with the live session's epoch", st["epoch"] == 5 and st["events"] == ["ready"]
      and st["version"] == "1.10.0" and st["connected"] is True and st["pending"])
check("active for that session only", zalo_push.active("c1", 5) and not zalo_push.active("c1", 6)
      and not zalo_push.active("c1", 0) and not zalo_push.active("other", 5))
check("take returns the pending wake-up once", zalo_push.take("c1") and not zalo_push.take("c1")
      and not zalo_push.pending("c1"))
os.environ["JAVIS_ZALO_PUSH"] = "0"
check("JAVIS_ZALO_PUSH=0: no variables and never active", zalo_push.env_for("c1") == {} and not zalo_push.active("c1", 5))
os.environ.pop("JAVIS_ZALO_PUSH")

src_store = (ROOT / "server" / "mcp_store.py").read_text(encoding="utf-8")
check("the variables are set where every caller resolves the connection (stdio zalo only)",
      'c.get("connector_id") == "zalo" and (c.get("transport") or "http") == "stdio"' in src_store
      and "zalo_push.env_for(c[\"id\"])" in src_store)

# ---- 2 to 5. the real read loop, small ticks ---------------------------------------------------------------
CONN = {"id": "zalo-1", "label": "Zalo một", "connector_id": "zalo"}
reads, flushes = [], {"khach": 0, "chu": 0}
state = {"alive": True, "epoch": 3, "during_read": None}


async def fake_read(conn):
    reads.append(time.time())
    hook, state["during_read"] = state["during_read"], None
    if hook:
        hook()
    await asyncio.sleep(0.01)
    return {"moi": 0, "trung": 0}


saved = {n: getattr(zc, n) for n in ("doc_mot_lan", "_ket_noi", "_cau_hinh", "push_active", "_epoch", "_history_turn",
                                     "_soi_tranh_phien", "_nhan_loi_moi", "xa_hang_cho", "xa_cho_chu", "NHIP", "NHIP_NHANH")}
real_push_active = zc.push_active
zc.doc_mot_lan = fake_read
zc._ket_noi = lambda: [dict(CONN)]
passes = [0]


def fake_cfg():
    passes[0] += 1          # the loop reads the settings once per pass, so this counts passes
    return {"zalo-1": True}


zc._cau_hinh = fake_cfg
zc._epoch = lambda conn: state["epoch"] if state["alive"] else 0
zc.push_active = lambda cid: state["alive"] and zalo_push.active(cid, state["epoch"])
zc._history_turn = lambda conn, tt, now=None: None
zc._soi_tranh_phien = lambda conn: None
zc._nhan_loi_moi = lambda conn: None
zc.xa_hang_cho = lambda cid, luc=None: flushes.__setitem__("khach", flushes["khach"] + 1) or 0
zc.xa_cho_chu = lambda cid, luc=None: flushes.__setitem__("chu", flushes["chu"] + 1) or 0
TICK = 0.2
zc.NHIP, zc.NHIP_NHANH = TICK, 0.05


async def loop_tests():
    zalo_push.forget()
    zc._TT.clear()
    zc._GOM.clear()
    zc._CHO_CHU.clear()
    zc.start()
    try:
        # 2. No wake-up ever came: read on the timer, as before.
        await asyncio.sleep(TICK * 4.5)
        n_timer = len(reads)
        check("an account that does not push is read every tick", 4 <= n_timer <= 7, n_timer)
        check("on the timer the held turns are released by the read, not by the idle pass", flushes == {"khach": 0, "chu": 0},
              flushes)

        # 3 and 4. The first wake-up ("ready") makes it a pushing account: one read for the wake-up, then NOTHING.
        t0 = time.time()
        r = zc.on_push("zalo-1", {"events": ["ready"], "version": "1.10.0", "connected": True})
        check("a wake-up for a known connection is accepted", r == {"ok": True, "known": True}, r)
        await asyncio.sleep(0.08)
        check("the wake-up is read at once, well inside one tick",
              len(reads) == n_timer + 1 and reads[-1] - t0 < TICK / 2, (len(reads) - n_timer, reads[-1] - t0))
        n, p0 = len(reads), passes[0]
        await asyncio.sleep(TICK * 6)
        check("a pushing account with nothing pending is not read at all", len(reads) == n, len(reads) - n)
        check("and the loop itself does not run: no tick while there is nothing to do", passes[0] == p0, passes[0] - p0)
        check("with nothing on hold nothing is flushed either", flushes == {"khach": 0, "chu": 0}, flushes)

        t0 = time.time()
        zc.on_push("zalo-1", {"events": ["messages"], "cursor": 9})
        await asyncio.sleep(0.08)
        check("a message wake-up is one read, at once", len(reads) == n + 1 and reads[-1] - t0 < TICK / 2,
              (len(reads) - n, reads[-1] - t0))

        # A wake-up that lands WHILE a read runs must cause one more read, not be swallowed by that read.
        n = len(reads)
        state["during_read"] = lambda: zc.on_push("zalo-1", {"events": ["messages"], "cursor": 10})
        zc.on_push("zalo-1", {"events": ["messages"], "cursor": 9})
        await asyncio.sleep(0.15)
        check("a wake-up during a read is followed by exactly one more read", len(reads) == n + 2, len(reads) - n)
        p0 = passes[0]
        await asyncio.sleep(TICK * 3)
        check("and then the loop is asleep again", len(reads) == n + 2 and passes[0] == p0, (len(reads) - n, passes[0] - p0))

        # A turn put on hold (from anywhere, here outside the loop): the loop ticks only until it is released.
        n = len(reads)
        zc._xep_cho("zalo-1", {"external_chat_id": "u9", "created_at": time.time(), "text": "alo"})
        check("a held turn is in the queue", ("zalo-1", "u9") in zc._GOM)
        await asyncio.sleep(0.3)
        check("a turn on hold makes the loop tick and flush, with no read", flushes["khach"] >= 2 and len(reads) == n,
              (flushes, len(reads) - n))
        zc._GOM.clear()                         # released
        await asyncio.sleep(0.15)
        p0, f0 = passes[0], dict(flushes)
        await asyncio.sleep(TICK * 3)
        check("once it is released the loop sleeps again", passes[0] == p0 and flushes == f0, (passes[0] - p0, flushes))

        zc._giu_cho_chu("zalo-1", {"external_chat_id": "u7", "created_at": time.time(), "text": "anh ơi"})
        await asyncio.sleep(TICK * 2.5)
        check("a turn held for the owner makes the loop tick on the normal interval", flushes["chu"] > f0["chu"], flushes)
        zc._CHO_CHU.clear()
        await asyncio.sleep(TICK * 1.5)

        # Other things that give the loop work wake it at once.
        for name, fn in (("a bot taking its post", lambda: zc.dang_ky_bot("zalo-9", object())),
                         ("a bot leaving its post", lambda: zc.huy_dang_ky_bot("zalo-9")),
                         ("a connection saved on the Connections page", lambda: [f() for f in list(mcp_store.ON_SAVE)])):
            await asyncio.sleep(0.05)
            p0 = passes[0]
            fn()
            await asyncio.sleep(0.05)
            check(f"{name} wakes the loop", passes[0] > p0, passes[0] - p0)
        check("the loop asked to be told about saved connections and ended MCP processes",
              zc.wake in mcp_store.ON_SAVE and zc._on_mcp_exit in mcp_client.STDIO_EXIT_LISTENERS)

        # 5. The process died: the exit listener wakes the loop, which reads at once (that read restarts javis-zalo).
        await asyncio.sleep(0.1)
        n = len(reads)
        state["alive"] = False
        t0 = time.time()
        for f in list(mcp_client.STDIO_EXIT_LISTENERS):
            f("zalo-1")
        await asyncio.sleep(0.08)
        check("a pushing account whose process ended is read at once, not on a tick",
              len(reads) >= n + 1 and reads[n] - t0 < TICK / 2, (len(reads) - n, reads[-1] - t0))
        p0 = passes[0]
        zc._on_mcp_exit("some-other-mcp")
        await asyncio.sleep(0.05)
        check("another MCP server's process ending does not wake the Zalo loop", passes[0] == p0, passes[0] - p0)
        state["alive"], state["epoch"] = True, 4       # restarted: a new session that has not called yet
        n = len(reads)
        await asyncio.sleep(TICK * 2.5)
        check("the restarted process is read on the timer until its own wake-up arrives", len(reads) >= n + 2, len(reads) - n)
        zc.on_push("zalo-1", {"events": ["ready"]})
        await asyncio.sleep(0.1)
        n, p0 = len(reads), passes[0]
        await asyncio.sleep(TICK * 3)
        check("after its wake-up it is a pushing account again: no read, no tick", len(reads) == n and passes[0] == p0,
              (len(reads) - n, passes[0] - p0))

        r = zc.on_push("no-such-conn", {"events": ["messages"]})
        check("a wake-up for an unknown connection records nothing", r == {"ok": True, "known": False}
              and zalo_push.state("no-such-conn") == {}, (r, zalo_push.state("no-such-conn")))
    finally:
        zc.stop()
        zc._GOM.clear()
        zc._CHO_CHU.clear()
        zc._BOTS.pop("zalo-9", None)


asyncio.run(loop_tests())
for name, value in saved.items():
    setattr(zc, name, value)

check("with no live MCP session an account is never 'pushing' (the real check)", real_push_active("zalo-1") is False)

# ---- 6. the route -------------------------------------------------------------------------------------------
import main  # noqa: E402


class FakeRequest:
    def __init__(self, host="127.0.0.1", auth="", body=b"{}", headers=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"authorization": auth, **(headers or {})}
        self._body = body

    async def body(self):
        return self._body


seen = []
real_on_push = zc.on_push
zc.on_push = lambda conn, body: seen.append((conn, body)) or {"ok": True, "known": True}


def call(**kw):
    conn = kw.pop("conn", "zalo-1")
    out = asyncio.run(main.zalo_push_wake(FakeRequest(**kw), conn=conn))
    return getattr(out, "status_code", 200), out


good = "Bearer " + tok
try:
    code, out = call(auth=good, body=json.dumps({"events": ["messages"], "cursor": 3}).encode())
    check("a local call with this process's bearer reaches the loop", code == 200 and out == {"ok": True, "known": True}
          and seen == [("zalo-1", {"events": ["messages"], "cursor": 3})], (code, seen))
    seen.clear()
    check("without the bearer: 401, nothing recorded", call(auth="")[0] == 401 and call(auth="Bearer wrong")[0] == 401 and not seen)
    check("from another machine: 403, even with the bearer", call(host="203.0.113.9", auth=good)[0] == 403 and not seen)
    check("through a tunnel or proxy on this machine: 403",
          call(auth=good, headers={"x-forwarded-for": "203.0.113.9"})[0] == 403 and not seen)
    check("an oversized body is refused", call(auth=good, body=b"x" * (main.ZALO_PUSH_MAX_BODY + 1))[0] == 413 and not seen)
    code, _ = call(auth=good, body=b"not json")
    check("a body that is not JSON is still a wake-up, with nothing in it", code == 200 and seen == [("zalo-1", {})], seen)
finally:
    zc.on_push = real_on_push
check("the route is reachable without a session cookie (it has its own checks)", "/zalo/push" in main._AUTH_PUBLIC_EXACT)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
