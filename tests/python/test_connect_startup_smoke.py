"""After a restart or an update, Javis pings every connection once and tells the owner what is broken.

    python tests/run.py connect_startup_smoke      (no network; spawns small Python servers)

Field report 2026-10-13 to 10-16: a connector broke during a container rebuild and nobody knew for
three and a half days. The periodic health sweep only colours the Connections page, which nobody
opens right after an update.

Locked here: one notice listing only the sources that still fail after a second chance; a source
that was merely slow to start (first download) is not reported; nothing is sent when all is well;
a source still starting reads as "starting", not as an error; Node's MODULE_NOT_FOUND reads as a
broken install that Check repairs, not as a generic start failure.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-smoke-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["HOME"] = str(_TMP / "home")
for _d in ("state", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)

import connect_health  # noqa: E402
import mcp_client  # noqa: E402
import mcp_store  # noqa: E402

HELPER = str(Path(__file__).resolve().parent / "_slow_start_mcp_server.py")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def conn(cid, label, delay=0.0, command=None):
    marker = _TMP / f"m-{cid}"
    marker.mkdir(exist_ok=True)
    return {"id": cid, "connector_id": "custom", "label": label, "transport": "stdio", "url": "",
            "command": command or sys.executable,
            "args": [HELPER, "--delay", str(delay), "--marker", str(marker)], "headers": {}, "env": {},
            "secrets": {}, "config": {}, "perm": "readonly", "deny_tools": [], "enabled": True, "auth": None}


notices = []


async def notify(text):
    notices.append(text)


connect_health.on_connections_down = notify
connect_health._CHECK_TIMEOUT = 0.5      # one ping; the slow source needs more than that


async def main():
    good = conn("good", "Good source")
    slow = conn("slow", "Slow first start", delay=1.2)
    broken = conn("broken", "Broken source", command=str(_TMP / "no-such-binary"))

    # --- one broken, one slow on its first start, one fine ---
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(slow), dict(broken)]
    first = await connect_health.check_one(dict(slow))
    check("first ping of a source still starting reads as 'starting', not as an error",
          first.get("kind") == "starting" and not first.get("ok"), first)
    report = await connect_health.startup_smoke("9.9.9", retry_after=1.5)
    check("smoke test checked every enabled source", report.get("checked") == 3, report)
    check("the slow first start got a second chance and is not reported",
          [f["id"] for f in report.get("failed", [])] == ["broken"], report.get("failed"))
    check("exactly one notice to the owner", len(notices) == 1, notices)
    text = notices[0] if notices else ""
    check("the notice names the broken source and the version",
          "Broken source" in text and "9.9.9" in text and "Slow first start" not in text, text)
    check("last_smoke() keeps the report for the Connections page",
          connect_health.last_smoke().get("failed") == report.get("failed"))
    await mcp_client.pool.close_all()

    # --- everything fine: no notice at all ---
    notices.clear()
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good)]
    report = await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("all sources up: no notice", report.get("ok") == 1 and not report.get("failed") and notices == [],
          (report, notices))
    await mcp_client.pool.close_all()

    # --- the same failure on two restarts in a row: one notice, not one per restart ---
    notices.clear()
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(broken)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("broken after a restart that was clean: reported", len(notices) == 1, notices)
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("still the same broken source after the next restart: not reported again", len(notices) == 1, notices)
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(broken)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("fixed, then broken again: reported again", len(notices) == 2, notices)
    await mcp_client.pool.close_all()

    # --- no dedicated hook: the notice goes through the owner hook main.py already wires ---
    engine_notices = []

    async def engine_notify(text):
        engine_notices.append(text)

    connect_health.on_connections_down = None
    connect_health.on_engine_down = engine_notify
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(broken)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("without a dedicated hook the notice uses the owner hook (on_engine_down)",
          len(engine_notices) == 1 and "Broken source" in engine_notices[0], engine_notices)
    connect_health.on_connections_down = notify
    await mcp_client.pool.close_all()

    # --- no notifier wired yet: the failure set is not remembered as told, so a later restart
    #     with a notifier still reports it ---
    notices.clear()
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)       # clean start resets the state
    saved_hook, saved_engine = connect_health.on_connections_down, connect_health.on_engine_down
    connect_health.on_connections_down = None
    connect_health.on_engine_down = None
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(broken)]
    report = await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("no notifier wired: the report says nothing was sent", report.get("notified") is False, report)
    check("and the failure set is not saved as already reported",
          connect_health._last_notified() == [], connect_health._last_notified())
    connect_health.on_connections_down, connect_health.on_engine_down = saved_hook, saved_engine
    report = await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("next restart with a notifier: the same failure set is reported after all",
          len(notices) == 1 and "Broken source" in notices[0] and report.get("notified") is True,
          (notices, report.get("notified")))
    check("and only then is it saved as reported", connect_health._last_notified() == ["broken:spawn"],
          connect_health._last_notified())

    # --- a notice that fails to send is not saved as reported either ---
    notices.clear()
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good)]
    await connect_health.startup_smoke("9.9.9", retry_after=0.1)

    async def failing_notify(text):
        raise RuntimeError("channel down")

    connect_health.on_connections_down = failing_notify
    mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(good), dict(broken)]
    report = await connect_health.startup_smoke("9.9.9", retry_after=0.1)
    check("a notice that failed is not saved as reported",
          report.get("notified") is False and connect_health._last_notified() == [],
          (report.get("notified"), connect_health._last_notified()))
    connect_health.on_connections_down = notify
    await mcp_client.pool.close_all()

    # --- the 2026-10-13 error text ---
    err = "RuntimeError: process đóng stdout (Error: Cannot find module 'ajv' | code: 'MODULE_NOT_FOUND')"
    npx_conn = {"command": "npx", "args": ["-y", "mcp-server-gsc@latest"]}
    kind, msg = connect_health.classify_error(err, npx_conn)
    check("MODULE_NOT_FOUND on an npx connector reads as a broken install that Check repairs",
          kind == "install" and "Kiểm tra" in msg, (kind, msg))
    check("and it has an English text for English screens", msg in connect_health._EN)
    # npx_cache leaves a folder touched in the last QUIET_SECONDS alone, so a Check right away
    # would repair nothing: the text says to wait first.
    check("it tells the user to wait about two minutes before Check (the npx quiet window)",
          "hai phút" in msg and "two minutes" in connect_health._EN.get(msg, ""), msg)
    kind2, _ = connect_health.classify_error(err, {"command": "node", "args": ["/srv/x.js"]})
    check("not an npx connector: Check cannot repair it, so no such promise", kind2 != "install", kind2)


asyncio.run(main())

print()
if fails:
    print(f"RED {len(fails)}: " + "; ".join(fails[:4]))
    raise SystemExit(1)
print("All green.")
