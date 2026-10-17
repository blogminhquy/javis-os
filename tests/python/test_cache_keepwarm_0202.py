"""0.202.0: prompt-cache keep-warm pings a Claude Code chat only when switched on, inside its window,
not while busy, and stops on a cold ping or a usage limit.

Run:
    python tests/run.py cache_keepwarm
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio

import cache_keepwarm as ck  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


clock = {"t": 1_000_000.0}


class Eng:
    def __init__(self, res):
        self.res, self.calls = res, 0

    async def warm_ping(self):
        self.calls += 1
        return dict(self.res)


state = {"on": False, "busy": set()}
kw = ck.KeepWarm(enabled=lambda: state["on"], window_min=lambda: 120, busy=lambda k: k in state["busy"],
                 now=lambda: clock["t"])
warm = Eng({"ok": True, "cache_read": 60000, "cache_write": 50})


async def main():
    kw.note_turn("s1", warm, prefix_tokens=60000)
    clock["t"] += ck.PING_AFTER_S + 1
    check("off by default: nothing pinged", await kw.tick() == 0 and warm.calls == 0)
    state["on"] = True
    state["busy"].add("s1")
    check("busy chat not pinged", await kw.tick() == 0)
    state["busy"].clear()
    check("due chat pinged once", await kw.tick() == 1 and warm.calls == 1)
    check("not again right away", await kw.tick() == 0)
    clock["t"] += ck.PING_AFTER_S + 1
    check("pinged again after the interval", await kw.tick() == 1 and warm.calls == 2)
    clock["t"] += 121 * 60
    check("window over: no more pings", await kw.tick() == 0 and "s1" not in kw.windows)

    cold = Eng({"ok": True, "cache_read": 0, "cache_write": 60000})
    kw.note_turn("s2", cold, prefix_tokens=60000)
    clock["t"] += ck.PING_AFTER_S + 1
    await kw.tick()
    clock["t"] += ck.PING_AFTER_S + 1
    check("cold ping stops the window", await kw.tick() == 0 and cold.calls == 1)

    lim = Eng({"ok": False, "limit": True, "reason": "usage limit"})
    kw.note_turn("s3", lim, prefix_tokens=60000)
    kw.note_turn("s4", Eng({"ok": True, "cache_read": 1, "cache_write": 0}), prefix_tokens=60000)
    clock["t"] += ck.PING_AFTER_S + 1
    await kw.tick()
    clock["t"] += ck.PING_AFTER_S + 1
    check("usage limit stops every window", kw.limited_until_real and await kw.tick() == 0)
    kw.note_turn("s5", warm, prefix_tokens=60000)
    check("a real message lifts the limit stop", not kw.limited_until_real)

    small = Eng({"ok": True, "cache_read": 1, "cache_write": 0})
    kw.note_turn("s6", small, prefix_tokens=500)
    clock["t"] += ck.PING_AFTER_S + 1
    await kw.tick()
    check("small prefix not worth a ping", small.calls == 0)
    check("warm rule", ck.ping_was_warm(1000, 50) and not ck.ping_was_warm(1000, 500) and not ck.ping_was_warm(0, 0))
    check("status reports", kw.status()["enabled"] is True and isinstance(kw.status()["recent"], list))

asyncio.run(main())

import main as app_main  # noqa: E402
from _paths import moi_duong_dan  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

check("keep-warm off by default", app_main._KEEPWARM.enabled() is False)
check("routes registered", {"/cache-keepwarm"} <= moi_duong_dan(app_main.app))
c = TestClient(app_main.app, base_url="http://127.0.0.1:8080")
r = c.post("/cache-keepwarm", json={"enabled": True, "window_min": 5})
check("switch on, window clamped to 30 minutes", r.json().get("enabled") is True and r.json().get("window_min") == 30)
check("status reflects the switch", c.get("/cache-keepwarm").json()["enabled"] is True)
c.post("/cache-keepwarm", json={"enabled": False})
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("only subscription chats are noted", "claude_auth.che_do() == claude_auth.SUBSCRIPTION" in src
      and "_KEEPWARM.note_turn(conv_sid, cli" in src)
eng = (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("ping forks without saving and denies tools", "fork_session = True" in eng and "no-session-persistence" in eng
      and "PermissionResultDeny" in eng and "max_turns = 1" in eng)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
