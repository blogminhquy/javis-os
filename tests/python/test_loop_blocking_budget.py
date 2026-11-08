"""The event loop serves people, not disk work (2026-11-08, performance stage 3).

Owner, 2026-11-08: pages and chat switches "delay mấy giây". Javis runs every page, chat turn, hub call and background
job on ONE asyncio loop, so a SQLite or file call made inside an `async def` freezes every click until it returns
(measured: the Kanban dispatcher, 0.3-1.2 s at a time). Stage 0 and 3 moved the known ones to worker threads (347 call
sites down to 218); this keeps it that way.

tools/loop_audit.py counts, per server module, the blocking calls made directly inside an `async def`. This test fails
when a module's count goes UP against loop_blocking_budget.json, and names the new call sites. Fix: hand the work to a
thread (`await asyncio.to_thread(fn, ...)`), or make a route that never awaits a plain `def` (FastAPI then runs it in
its thread pool). A count that went DOWN passes; record it with

    python tests/python/test_loop_blocking_budget.py --update

so the gain cannot slip back.

    python tests/run.py loop_blocking_budget
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import sys

sys.path.insert(0, str(ROOT / "tools"))
import loop_audit  # noqa: E402

BUDGET = ROOT / "tests" / "python" / "loop_blocking_budget.json"

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"\n{extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


found = loop_audit.audit()
now = loop_audit.counts(found)

if "--update" in sys.argv:
    BUDGET.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {sum(now.values())} call sites in {len(now)} modules -> {BUDGET.name}")
    raise SystemExit(0)

budget = json.loads(BUDGET.read_text(encoding="utf-8"))
for mod, n in sorted(now.items()):
    cap = budget.get(mod, 0)
    sites = "\n".join(f"    server/{mod}:{line} {fn}: {call}" for line, fn, call in found.get(mod, []))
    check(f"{mod}: {n} blocking calls on the event loop (budget {cap})", n <= cap,
          f"  New blocking work inside an async function. Hand it to a thread or make the route a plain def:\n{sites}")
lower = {m: (budget[m], now.get(m, 0)) for m in budget if now.get(m, 0) < budget[m]}
if lower:
    print("note: fewer than the budget in " + ", ".join(f"{m} ({a} -> {b})" for m, (a, b) in sorted(lower.items()))
          + ": run with --update to lock the gain in")
check("the budget only ever goes down from the stage 3 level (218)", sum(budget.values()) <= 218, sum(budget.values()))

# The audit itself: it must see a blocking call, and ignore one handed to a thread or made in a nested function.
import ast  # noqa: E402
probe = ast.parse('''
async def handler(store, p):
    store.append_message(1)
    p.read_text()
    await asyncio.to_thread(store.get_messages, 1)
    def inner():
        return p.read_text()
    return await asyncio.to_thread(inner)
''').body[0]
calls = [c for _, c in loop_audit.blocking_calls(probe)]
check("the audit counts direct blocking calls and nothing handed to a thread", calls == ["store.append_message", "p.read_text"], calls)
for name in ("tools/loop_audit.py", "tests/python/test_loop_blocking_budget.py"):
    s = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_loop_blocking_budget")
raise SystemExit(1 if fails else 0)
