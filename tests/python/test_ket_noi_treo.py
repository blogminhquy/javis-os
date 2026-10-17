"""0.194.0: "Mất kết nối tới máy chủ" lasting minutes (owner, 17/10/2026).

    python tests/run.py ket_noi_treo

- chat_runtime: one page with a stuck socket no longer holds the running turn and every other page.
- loop_watch: a freeze of the event loop is caught with the stack that caused it; an unclean restart is recorded.
- claude_sdk_engine builds its options off the loop; the page retries a handshake stuck in CONNECTING.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time

import chat_runtime  # noqa: E402
import loop_watch  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ═════ chat_runtime fan-out ═════
chat_runtime.SEND_WAIT_S = 0.2
chat_runtime.STUCK_S = 0.6


async def fanout():
    rt = chat_runtime.ChatRuntime()
    good, slow, dropped = [], [], []
    hang = asyncio.Event()
    gate = asyncio.Event()

    async def w_good(ev):
        good.append(ev["n"])

    async def w_dead(ev):
        await hang.wait()          # a socket that never finishes a send

    async def w_slow(ev):
        if ev["n"] == 0:
            await gate.wait()      # slow on the first event only, then fine
        slow.append(ev["n"])

    rt.add_client("good", w_good)
    rt.add_client("dead", w_dead, lambda: dropped.append("dead"))
    rt.add_client("slow", w_slow)
    t0 = time.monotonic()
    await rt.publish({"type": "x", "n": 0})
    first = time.monotonic() - t0
    out = {"first": first, "good_after_first": list(good)}
    for n in (1, 2, 3):
        t1 = time.monotonic()
        await rt.publish({"type": "x", "n": n})
        out.setdefault("next", []).append(time.monotonic() - t1)
    gate.set()
    await asyncio.sleep(0.05)
    out["slow_mid"] = list(slow)
    await asyncio.sleep(0.7)          # the dead page is now stuck past STUCK_S
    await rt.publish({"type": "x", "n": 4})
    await asyncio.sleep(0.05)
    out.update(good=list(good), slow=list(slow), dropped=list(dropped), clients=sorted(rt._clients))
    hang.set()
    await asyncio.sleep(0.05)
    return out


r = asyncio.run(fanout())
check("a page whose send hangs holds publish at most SEND_WAIT_S", r["first"] < 0.5, r["first"])
check("a healthy page gets the event before publish returns", r["good_after_first"] == [0], r)
check("later events do not wait for the stuck page at all", all(x < 0.1 for x in r["next"]), r["next"])
check("a slow page that recovers gets every event, in order", r["slow"] == [0, 1, 2, 3, 4], r["slow"])
check("the healthy page got every event in order", r["good"] == [0, 1, 2, 3, 4], r["good"])
check("a page stuck past STUCK_S is dropped and its socket closed (on_drop)", r["dropped"] == ["dead"]
      and r["clients"] == ["good", "slow"], r)


async def dead_raises():
    rt = chat_runtime.ChatRuntime()
    got = []

    async def w_err(ev):
        raise ConnectionResetError("tab closed")

    async def w_ok(ev):
        got.append(ev["n"])
    rt.add_client("err", w_err)
    rt.add_client("ok", w_ok)
    await rt.publish({"n": 1})
    await rt.publish({"n": 2})
    return got, sorted(rt._clients)


got, clients = asyncio.run(dead_raises())
check("a page whose send raises does not stop the others", got == [1, 2], got)

# ═════ loop_watch ═════
loop_watch.BLOCK_S = 0.3
state = tempfile.mkdtemp(prefix="javis-loopwatch-")


def frozen_here():
    time.sleep(0.9)    # synchronous work on the loop


async def watch():
    loop_watch.start(state_dir=state)
    await asyncio.sleep(0.3)
    frozen_here()
    await asyncio.sleep(0.6)
    return loop_watch.report()


rep = asyncio.run(watch())
inc = rep["incidents"][0] if rep["incidents"] else {}
check("a freeze of the loop is recorded", rep["running"] and len(rep["incidents"]) == 1, rep)
check("the record names the code that froze it", any("frozen_here" in ln for ln in inc.get("stack", [])), inc)
check("the record ends once the loop is free, with its length", inc.get("ended") and inc.get("seconds", 0) >= 0.5, inc)
check("no unclean restart on a first boot", rep["unclean_restarts"] == [], rep)

# The previous run died without a clean stop: the next boot records it.
import json  # noqa: E402
beat = os.path.join(state, "loop_beat.json")
with open(beat, "w", encoding="utf-8") as f:
    json.dump({"pid": 999999, "alive": 1700000000.0, "clean": False}, f)
loop_watch._note_restart(state)
rs = loop_watch.report()["unclean_restarts"]
check("a boot after a crash records the unclean restart with when it was last alive",
      len(rs) == 1 and rs[0]["last_alive"] == 1700000000.0 and rs[0]["pid"] == 999999, rs)
loop_watch.stop()
loop_watch._note_restart(state)
check("a clean stop is not counted as a crash", len(loop_watch.report()["unclean_restarts"]) == 1)

# ═════ sources ═════
sdk = (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("claude_sdk_engine builds options off the event loop", "options = await asyncio.to_thread(self._options)" in sdk
      and "options = self._options()" not in sdk)
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("the chat socket registers a drop hook that closes it", "_CHAT_RUNTIME.add_client(client_id, send_client, _drop_client)"
      in main_src)
check("the server starts the watchdog and exposes /health/loop", "loop_watch.start(state_dir=" in main_src
      and '@app.get("/health/loop")' in main_src)
app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("the page retries a handshake stuck in CONNECTING", "WS_MO_MS" in app_js
      and "dangMo.readyState === WebSocket.CONNECTING" in app_js)
check("the page waits 20s for a pong before dropping a socket", "WS_PONG_MS = 20000" in app_js)
for name in ("server/loop_watch.py", "server/chat_runtime.py"):
    src = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", "—" not in src and "–" not in src)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_ket_noi_treo")
raise SystemExit(1 if fails else 0)
