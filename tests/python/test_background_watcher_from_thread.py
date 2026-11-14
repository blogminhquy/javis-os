"""Background terminal job registered from a worker thread still gets watched (issue 1392).

    python tests/run.py background_watcher_from_thread

An API engine's `javis_terminal background=true` reaches `coding_terminal.chay_nen` through
`asyncio.to_thread` in the hub. `tien_trinh_nen.theo_doi_nhom` then registered the job but could
not start the watcher (no running loop in that thread), so the job stayed "running" forever and
the chat was never told it finished, until the next server restart. This test runs that exact
path on a live loop with a real process group.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-bgwatch-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_terminal as ct  # noqa: E402
import tien_trinh_nen as T  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if os.name == "nt" or not ct._git_bash():
    print("skip: process groups and a real bash are POSIX only")
    print("OK - test_background_watcher_from_thread: skipped")
    sys.exit(0)

T.NHIP_GIAY = 0.2          # poll fast so the test does not wait seconds per tick
WS = Path(_TMP) / "project"
WS.mkdir(parents=True)
G = [str(WS.resolve())]


def watchers(loop):
    return [t for t in asyncio.all_tasks(loop)
            if getattr(t.get_coro(), "__name__", "") == "_vong_theo_doi" and not t.done()]


async def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return bool(cond())


async def main():
    loop = asyncio.get_running_loop()
    done = []

    async def on_done(v):
        done.append(v)

    T.dat_khi_xong(on_done)
    T.khoi_dong()           # the server's startup event: runs on the loop, nothing to watch yet
    check("startup remembers the server loop", getattr(T, "_LOOP", None) is loop)
    check("no job yet: no watcher", not watchers(loop))

    # ---- 1. The hub path: chay_nen in a worker thread, exactly like mcp_hub's _terminal ----
    out = await asyncio.to_thread(ct.chay_nen, "sleep 0.6; echo done > out.txt", "s1", G, "",
                                  str(WS), "web:issue1392")
    check("background command started", "proc_" in out, out)
    jobs = T.dang_chay("web:issue1392")
    check("job registered in the registry", len(jobs) == 1, jobs)
    started = await wait_for(lambda: bool(watchers(loop)), 3)
    check("watcher task starts on the server loop although the job came from a thread", started)
    check("exactly one watcher", len(watchers(loop)) == 1, watchers(loop))

    reaped = await wait_for(lambda: not T.dang_chay("web:issue1392") and bool(done), 10)
    check("dead process group is reaped (job leaves the running list)", reaped, T.dang_chay())
    await asyncio.sleep(3 * T.NHIP_GIAY)
    mine = [v for v in done if v.get("chat_id") == "web:issue1392"]
    check("completion callback fires exactly once", len(mine) == 1, mine)
    check("reported as finished with the new file",
          bool(mine) and mine[0].get("trang_thai") == "xong"
          and any(f.endswith("out.txt") for f in mine[0].get("file_moi") or []), mine)
    stopped = await wait_for(lambda: not watchers(loop), 3)
    check("watcher rests once nothing is running", stopped)

    # ---- 2. Several threads at once still start a single watcher ----
    done.clear()
    outs = await asyncio.gather(*[
        asyncio.to_thread(ct.chay_nen, "sleep 0.5", f"s{i}", G, "", str(WS), f"web:many{i}")
        for i in range(2, 5)])
    check("three background commands started", all("proc_" in o for o in outs), outs)
    await wait_for(lambda: bool(watchers(loop)), 3)
    check("concurrent registrations share one watcher", len(watchers(loop)) == 1, watchers(loop))
    await wait_for(lambda: not T.dang_chay() and len(done) >= 3, 10)
    ids = [v["id"] for v in done]
    check("each of them reported exactly once", len(ids) == 3 and len(set(ids)) == 3, ids)

    # ---- 3. Adopting on the loop itself (nhan_nuoi_theo_tag) still works ----
    done.clear()
    import subprocess
    p = subprocess.Popen(["sh", "-c", "(sleep 0.5) &\nexit 0"], cwd=str(WS), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.wait()
    T.ghi_nhom("chat:adopt:1", p.pid)
    adopted = T.nhan_nuoi_theo_tag("chat:adopt:1", str(WS), "web:adopt")
    check("left-behind group adopted from the loop", len(adopted) == 1, adopted)
    check("watcher started directly on the loop", len(watchers(loop)) == 1)
    await wait_for(lambda: bool(done), 10)
    check("adopted job reported once", [v["chat_id"] for v in done] == ["web:adopt"], done)
    return loop


loop = asyncio.run(main())

# ---- 4. Fail safe: the server loop is gone, a thread registers a job ----
check("the remembered loop is closed after the run", getattr(T, "_LOOP", None) is loop and loop.is_closed())
err = []


def from_thread():
    try:
        T._dam_bao_vong()
    except Exception as e:      # noqa: BLE001
        err.append(e)

th = threading.Thread(target=from_thread)
th.start()
th.join()
check("closed loop: no crash from a worker thread", not err, err)
try:
    T._dam_bao_vong()
    ok = True
except Exception:              # noqa: BLE001
    ok = False
check("closed loop: no crash without any loop", ok)

src = (SERVER / "tien_trinh_nen.py").read_text(encoding="utf-8")
check("hand-off to the server loop is thread safe", "call_soon_threadsafe(_dam_bao_vong)" in src)

print()
if _fails:
    print(f"FAIL - test_background_watcher_from_thread: {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_background_watcher_from_thread: all pass")
