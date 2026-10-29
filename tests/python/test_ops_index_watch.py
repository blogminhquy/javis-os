"""Javis/index.md stays current in EVERY brain, rebuilt only when its inputs change (0.389.0).

    python tests/run.py ops_index_watch      (no network)

The bug: the scheduler rebuilt the operations index only for brains the loop scheduler knew (the default brain and
brains that once had a loop). A brain with no loop kept the index from the day it was created: "0 agents" while it
had 18. The fix sweeps every brain but rebuilds only those whose stat-only signature moved, a few per tick.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-opsidx-state-"))

import ops_index_watch as w  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    # Bump mtime past the filesystem's resolution so an edit within the same tick still shows.
    t = time.time() + write.n
    write.n += 1
    os.utime(p, (t, t))
    os.utime(p.parent, (t, t))


write.n = 1


# ---- 1. The signature moves with every input the index lists, and with nothing else ----
root = Path(tempfile.mkdtemp(prefix="javis-opsidx-brain-"))
(root / "Javis").mkdir()


def sig():
    return w.brain_signature(root, root / "agents", root / "workflows", root / "plugins")


s0 = sig()
check("signature is stable when nothing changes", sig() == s0)
write(root / "notes" / "idea.md", "a note")
check("a note outside the capability folders does not move it", sig() == s0)

steps = [
    ("adding an agent", lambda: write(root / "agents" / "seller.md", "---\nname: Seller\n---\n")),
    ("editing an agent", lambda: write(root / "agents" / "seller.md", "---\nname: Seller v2\n---\n")),
    ("adding a workflow", lambda: write(root / "workflows" / "daily.md", "---\nname: Daily\n---\n")),
    ("adding a skill", lambda: write(root / "skills" / "email" / "SKILL.md", "---\nname: email\n---\n")),
    ("disabling a skill", lambda: (root / "skills" / ".disabled").mkdir() or
     (root / "skills" / "email").rename(root / "skills" / ".disabled" / "email")),
    ("adding a loop", lambda: write(root / "Javis" / "loops" / "watch.md", "---\nname: Watch\n---\n")),
    ("a loop pausing itself", lambda: write(root / "Javis" / "loop-state.json", "{}")),
    ("adding a brain plugin", lambda: write(root / "plugins" / "calc" / "plugin.yaml", "name: calc\n")),
    ("editing the index by hand", lambda: write(root / "Javis" / "index.md", "x")),
    ("deleting the index by hand", lambda: (root / "Javis" / "index.md").unlink()),
]
for label, act in steps:
    before = sig()
    act()
    check(f"{label} moves the signature", sig() != before)


# ---- 2. The watcher rebuilds only what changed, within a budget, oldest first ----
class Fake:
    def __init__(self):
        self.sigs, self.calls, self.fail = {}, [], set()
        self.now = 1000.0

    def signature_of(self, b):
        return self.sigs[b]

    def rebuild(self, b):
        self.calls.append(b)
        return {"ok": b not in self.fail}


f = Fake()
f.sigs = {f"b{i}": "s" for i in range(10)}
watch = w.IndexWatcher(f.signature_of, f.rebuild, max_rebuilds=4, refresh_s=600, clock=lambda: f.now)
brains = sorted(f.sigs)

first = watch.sweep(brains)
check("first sweep rebuilds at most the budget", len(first) == 4, first)
watch.sweep(brains)
watch.sweep(brains)
check("three sweeps cover all ten brains once", sorted(f.calls) == brains, f.calls)
f.calls.clear()
check("an unchanged brain is not rebuilt again", watch.sweep(brains) == [] and f.calls == [])

f.sigs["b7"] = "s2"
check("only the brain that changed is rebuilt", watch.sweep(brains) == ["b7"], f.calls)

f.fail.add("b3")
f.sigs["b3"] = "s2"
watch.sweep(brains)
f.fail.clear()
check("a failed rebuild is retried on the next sweep", watch.sweep(brains) == ["b3"])

shared = ["p1"]
watch2 = w.IndexWatcher(f.signature_of, f.rebuild, shared_signature=lambda: shared[0],
                        max_rebuilds=20, refresh_s=600, clock=lambda: f.now)
watch2.sweep(brains)
shared[0] = "p2"
check("a change every brain shares (a global plugin) rebuilds every brain",
      sorted(watch2.sweep(brains)) == brains)

f.now += 601
check("after refresh_s every brain is rebuilt anyway", sorted(watch2.sweep(brains)) == brains)

watch2.sweep(brains[:3])
check("a brain that is gone is forgotten", set(watch2._seen) == set(brains[:3]))


# ---- 3. Through main: a brain WITHOUT any loop gets its index updated (the reported bug) ----
import main  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="javis-opsidx-brains-"))
main.BRAINS_DIR = str(base)
psc = base / "PSC Advisor"
main._ensure_brain_scaffold(psc)
idx = psc / "Javis" / "index.md"
(base / "not-a-brain").mkdir()

main._ops_index_sweep()
check("index exists for a brain with no loop", idx.is_file())
check("it starts at 0 agents", "**Tổng quan:** 0 agents" in idx.read_text(encoding="utf-8"))
for i in range(18):
    write(psc / "agents" / f"agent-{i}.md", f"---\nname: Agent {i}\nrole: helper\n---\n")
main._ops_index_sweep()
text = idx.read_text(encoding="utf-8")
check("after new agents the next sweep lists all 18", "**Tổng quan:** 18 agents" in text, text[:300])
check("a folder that is not a brain gets no index", not (base / "not-a-brain" / "Javis").exists())

calls = []
real = main._OPS_INDEX_WATCH._rebuild
main._OPS_INDEX_WATCH._rebuild = lambda b: calls.append(b) or real(b)
main._ops_index_sweep()
check("a sweep with nothing changed does not rebuild", calls == [], calls)
main._OPS_INDEX_WATCH._rebuild = real

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_ops_index_watch: all pass")
