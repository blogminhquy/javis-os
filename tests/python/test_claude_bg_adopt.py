"""Claude Code's leftover background work is adopted and reported back (owner report 2026-11-04).

A long video render or edit started from the chat finished and nothing said so, in the chat or the bell. Claude Code's
`claude` stays warm between turns and its Bash tool runs every command in a new session, so the process group check
the other CLI engines rely on never saw what it left running. The engine now carries an environment mark
(tien_trinh_nen.ENV_MARK); these tests rebuild the real process layout with real processes.

    python tests/run.py claude_bg_adopt
"""
import os
import subprocess
import sys
import tempfile
import time

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cbga-")
import asyncio  # noqa: E402

import tien_trinh_nen as T  # noqa: E402
import turn_done_notice as N  # noqa: E402
import warm_pool  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- turn_done_notice (every platform) ----
os.environ.pop("JAVIS_LONG_TURN_NOTIFY_S", None)
check("a short turn does not ring", not N.should_notify(30, "hi", "answer"))
check("a turn of 3 minutes or more rings", N.should_notify(200, "make the video", "Here is the video"))
check("an empty answer never rings", not N.should_notify(900, "x", "  "))
check("a background job's follow-up rings however short",
      N.should_notify(5, N.FOLLOWUP_HEAD + " ffmpeg (4 phút).\nLàm tiếp: ...", "Done, link below"))
os.environ["JAVIS_LONG_TURN_NOTIFY_S"] = "0"
check("JAVIS_LONG_TURN_NOTIFY_S=0 keeps only follow-ups",
      not N.should_notify(5000, "x", "y") and N.should_notify(1, N.FOLLOWUP_HEAD, "y"))
os.environ["JAVIS_LONG_TURN_NOTIFY_S"] = "nonsense"
check("a broken threshold falls back to the default", N.threshold_s() == N.DEFAULT_THRESHOLD_S)
os.environ.pop("JAVIS_LONG_TURN_NOTIFY_S", None)
check("a long answer is cut for the bell", len(N.notice_text("a" * 5000)) <= N.MAX_BODY + 3)
src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("the follow-up turn opens with the shared head", "turn_done_notice.FOLLOWUP_HEAD} {mo_ta}" in src_main)
check("run_turn rings the bell for a long turn", "await _bao_luot_dai_xong(conv_sid, brain, turn_tag" in src_main)
check("the long-turn push stays quiet on a device showing Javis", "push_if_away=True" in src_main)
sw = (ROOT / "dashboard" / "sw.js").read_text(encoding="utf-8")
check("the service worker honours quiet_if_visible", "d.quiet_if_visible" in sw and "c.focused" in sw)


# ---- warm_pool.detach keeps the process ----
class _H(warm_pool.Handle):
    kind = "claude"

    def __init__(self):
        self.closed = False

    def alive(self):
        return not self.closed

    async def close(self):
        self.closed = True


async def _forget():
    os.environ["JAVIS_WARM_BUDGET_MB"] = "4000"
    pool = warm_pool.Pool()
    h = _H()
    slot = pool.admit("conv1", "claude", "fp", h)
    before = pool.peek("conv1") is slot
    pool.detach(slot)
    await asyncio.sleep(0.05)
    del os.environ["JAVIS_WARM_BUDGET_MB"]
    return before, pool.peek("conv1"), h.closed

before, left, closed = asyncio.run(_forget())
check("detach takes the slot out of the pool", before and left is None, (before, left))
check("detach does not close the process", closed is False)


# ---- claude_warm: the mark rides on the engine's options, and the process lingers for its tasks ----
import claude_warm  # noqa: E402


class _Opts:
    def __init__(self):
        self.env = {"ANTHROPIC_API_KEY": "k"}


class _Cli:
    tag = "chat:abc:1"

    def __init__(self):
        self.calls = 0

    def _options(self):
        self.calls += 1
        return _Opts()


cli = _Cli()
claude_warm.mark_background(cli, "sess-1")
claude_warm.mark_background(cli, "sess-1")
o = cli._options()
if T.POSIX:
    check("the engine starts with the mark in its environment", o.env.get(T.ENV_MARK) == "sess-1", o.env)
    check("its own environment is kept", o.env.get("ANTHROPIC_API_KEY") == "k")
    check("marking twice wraps once", cli.calls == 1)
    check("the turn's tag knows its mark", T._MARKS_BY_TAG.get("chat:abc:1") == ["sess-1"])
    T.bo_tag("chat:abc:1")
    check("bo_tag forgets the mark", "chat:abc:1" not in T._MARKS_BY_TAG)

from claude_agent_sdk import SystemMessage  # noqa: E402
import claude_sdk_engine as eng  # noqa: E402


class _Client:
    def __init__(self, msgs):
        self.msgs = msgs

    async def receive_messages(self):
        for m in self.msgs:
            await asyncio.sleep(0.01)
            yield m
        await asyncio.sleep(3600)


class _LH:
    def __init__(self, msgs):
        self.client = _Client(msgs)
        self.closed = False

    async def close(self):
        self.closed = True


async def _linger(msgs, cap=5.0):
    comp = eng._CompletionWatch(None)
    comp.tasks.add("t1")
    h = _LH(msgs)
    claude_warm._linger(h, comp, cap=cap)
    t0 = time.time()
    while not h.closed and time.time() - t0 < cap + 2:
        await asyncio.sleep(0.02)
    return h.closed, time.time() - t0

closed, took = asyncio.run(_linger([SystemMessage("task_notification", {"task_id": "t1", "status": "completed"})]))
check("a lingering process closes once its background task completes", closed and took < 2, took)
closed, took = asyncio.run(_linger([], cap=0.3))
check("a lingering process closes at its cap", closed and took < 2, took)
bw = (SERVER / "claude_warm.py").read_text(encoding="utf-8")
check("a turn that ends with tasks running lingers instead of closing",
      "elif linger and handle.alive():" in bw and "_linger(handle, completion)" in bw)

if not T.POSIX:
    print("SKIPPED the process tests: Windows has no process groups.")
    if fails:
        raise SystemExit(f"\nFAIL - test_claude_bg_adopt: {len(fails)}")
    print("\nOK - test_claude_bg_adopt")
    sys.exit(0)

WD = tempfile.mkdtemp(prefix="javis-cbga-wd-")


def marked_env(mark):
    return {**os.environ, T.ENV_MARK: mark}


# ---- 1. `nohup cmd &` from Claude Code's Bash tool: the shell (own session) exits, the command is orphaned ----
sh = subprocess.Popen(["sh", "-c", "(sleep 1.5; echo x > render.mp4) &\nexit 0"], cwd=WD, start_new_session=True,
                      env=marked_env("conv-A"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sh.wait()
time.sleep(0.2)
check("the orphaned command is found by its mark", len(T.groups_left_by_mark("conv-A")) == 1,
      T.groups_left_by_mark("conv-A"))
check("another conversation's mark sees nothing", T.groups_left_by_mark("conv-B") == [])
T.note_mark("chat:A:1", "conv-A")
T.dat_loi_dan("web:A", "add the audio and send the video")
check("co_nhom_song sees the marked work", T.co_nhom_song("chat:A:1"))
ds = T.nhan_nuoi_theo_tag("chat:A:1", WD, "web:A")
check("the end of the turn adopts it", len(ds) == 1, ds)
check("javis_job op=then is no longer dropped for Claude Code",
      bool(ds) and ds[0].get("sau_khi_xong") == "add the audio and send the video" and ds[0].get("noi_tiep"))
check("an adopted group is not adopted twice", T.groups_left_by_mark("conv-A") == [])
done = []
t0 = time.time()
while not done and time.time() - t0 < 8:
    time.sleep(0.3)
    done = T.kiem_mot_luot()
check("it is reported done when it ends", len(done) == 1 and done[0]["trang_thai"] == "xong", done)
check("the report lists the new file", bool(done) and any(f.endswith("render.mp4") for f in done[0]["file_moi"]))

# ---- 2. A process still owned by a live engine (an MCP server) is not the owner's background work ----
ENGINE = ("import subprocess,sys,time\n"
          "p = subprocess.Popen(sys.argv[1:], start_new_session=True)\n"
          "time.sleep(2.5)\n"
          "p.terminate()\n")
eng_p = subprocess.Popen([sys.executable, "-c", ENGINE, "sleep", "30"], env=marked_env("conv-C"))
time.sleep(0.4)
check("a server child of a live engine is left alone", T.groups_left_by_mark("conv-C") == [],
      T.groups_left_by_mark("conv-C"))
check("the engine itself (in the server's own group) is left alone",
      all(g != os.getpgrp() for g in T.groups_left_by_mark("conv-C")))

# ---- 3. A turn that ended while Claude Code still runs a background task: its shell is adopted ----
eng_q = subprocess.Popen([sys.executable, "-c", ENGINE, "bash", "-c", "sleep 1.8; true"], env=marked_env("conv-D"))
time.sleep(0.4)
check("a background task shell of a live engine is adopted", len(T.groups_left_by_mark("conv-D")) == 1,
      T.groups_left_by_mark("conv-D"))
eng_p.wait()
eng_q.wait()

# ---- 4. The report names the real command, not Claude Code's shell wrapper ----
wrapped = ("/bin/bash -c source /root/.claude/shell-snapshots/snapshot-bash-1-x.sh 2>/dev/null || true && "
           "eval 'ffmpeg -i in.mp4 -c:v libx264 out.mp4' < /dev/null && pwd -P >| /tmp/claude-ab12-cwd")
check("Claude Code's shell wrapper is unwrapped in the description",
      T.mo_ta_lenh([{"cmd": wrapped}]) == "ffmpeg -i in.mp4 -c:v libx264 out.mp4", T.mo_ta_lenh([{"cmd": wrapped}]))

if fails:
    raise SystemExit(f"\nFAIL - test_claude_bg_adopt: {len(fails)}")
print("\nOK - test_claude_bg_adopt")
