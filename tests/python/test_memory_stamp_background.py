"""A memory background work writes is not stamped with the source of a chat open at the same time (#1165).

    python tests/run.py memory_stamp_background

The note in #1165: after a chat turn, `stamp_new_facts` gave the chat's source to every memory changed since the turn
began, including one a Kanban job, reminder or loop wrote in the same brain meanwhile. Now such work marks itself
(`memory_control.background_writer`) and a memory changed while it ran is left without a source.

Pinned here:
  1. nothing else running: the chat stamps its memory
  2. a writer at `auto` or `full` in the same brain: a memory changed while it ran is not stamped
  3. a writer in another brain, a `suggest` writer, or one that ended before the change: the chat stamps
  4. Kanban jobs, reminders and loops run inside a writer span
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mem-bg-"))

import memory_control as mc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


base = Path(tempfile.mkdtemp(prefix="javis-mem-bg-brains-"))
brain = base / "Shop"
other = base / "Home"
mem = brain / "memory"
(mem / "facts").mkdir(parents=True)
(other / "memory" / "facts").mkdir(parents=True)


def fact(slug, mtime=None):
    f = mem / "facts" / f"{slug}.md"
    f.write_text("---\ntype: business\n---\nKhách sỉ lấy hàng thứ Hai.\n", encoding="utf-8")
    if mtime is not None:
        os.utime(f, (mtime, mtime))
    return f


def stamp():
    return mc.stamp_new_facts(mem, source="chat 2026-11-09 (abc12345)", since=time.time() - 60)


# 1. alone
mc._WRITER_SPANS.clear()
fact("mot")
check("1. nothing else running: the chat stamps its memory", "mot" in stamp())

# 2. a writer in the same brain
for mode in ("auto", "full"):
    mc._WRITER_SPANS.clear()
    with mc.background_writer(str(brain), mode):
        fact("hai-" + mode)
        got = stamp()
    check(f"2. a {mode} job writing in this brain: its memory is not stamped", "hai-" + mode not in got, got)
mc._WRITER_SPANS.clear()
with mc.background_writer(str(brain), "auto"):
    fact("sau")
got = stamp()
check("2. still unstamped after the job ended, when the change fell inside its run", "sau" not in got, got)

# 3. no overlap
mc._WRITER_SPANS.clear()
with mc.background_writer(str(other), "full"):
    fact("ba")
    got = stamp()
check("3. a job in another brain does not hold this brain's memories back", "ba" in got, got)
mc._WRITER_SPANS.clear()
with mc.background_writer(str(brain), "suggest"):
    fact("bon")
    got = stamp()
check("3. a suggest job only reads: no span, the chat stamps", "bon" in got and not mc._WRITER_SPANS, got)
mc._WRITER_SPANS.clear()
with mc.background_writer(str(brain), "auto"):
    pass
fact("nam", mtime=time.time() + 5)
got = stamp()
check("3. a job that ended before the change does not hold it back", "nam" in got, got)

# 4. wiring
for rel, needle in (("server/tasks.py", "memory_control.background_writer(task.get(\"brain_root\")"),
                    ("server/reminders.py", "memory_control.background_writer(self.deps.brain_root(brain), muc_quyen_cua(rem))"),
                    ("server/self_improve.py", "memory_control.background_writer(self.deps.brain_root(brain), loop.get(\"mode\")")):
    check(f"4. {rel} runs its work inside a writer span", needle in (ROOT / rel).read_text(encoding="utf-8"))

s = (ROOT / "tests" / "python" / "test_memory_stamp_background.py").read_text(encoding="utf-8")
check("no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
