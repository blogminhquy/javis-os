"""Count blocking work done directly on the server's event loop (2026-11-08, performance stage 3).

Javis serves every page, chat turn, MCP hub call and background job from ONE asyncio event loop. A blocking call made
inside an `async def` (a SQLite read or write, a file read or write, a directory scan, a subprocess, a sleep) freezes
every other click until it returns. That is what the owner felt as "delay mấy giây" (2026-11-08): the Kanban dispatcher
held the loop up to 1.2 s on a busy SQLite file.

This walks server/*.py and counts, per module, the calls of those kinds made inside an `async def` and NOT handed to a
worker thread (`asyncio.to_thread`, `run_in_executor`, `io_offload.run_io`, `run_in_threadpool`) and not inside a nested
function (those usually are what gets handed over). It is a static count, so it over-counts a little (a cheap call
that happens to match) and misses calls hidden behind a helper; it is a ratchet, not a profiler. The profiler is
GET /health/loop (server/loop_watch.py), on the real machine.

    python tools/loop_audit.py              # counts per module
    python tools/loop_audit.py tasks.py -v  # every call site of one module

tests/python/test_loop_blocking_budget.py fails when a module's count goes UP against
tests/python/loop_blocking_budget.json; `python tests/python/test_loop_blocking_budget.py --update` records a lower one.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"

# Calls that block: storage (SQLite through the stores), files, directory scans, processes, sleeps.
BLOCKING = re.compile(
    r"(^|\.)(get_store|store|_store|_db)\.|(^|\.)(get_store)$|\.execute(many|script)?$|"
    r"(^|\.)(read_text|write_text|read_bytes|write_bytes)$|^open$|^json\.(load|dump)$|"
    r"(^|\.)(_read_md|_write_md|_atomic_write_text|_atomic_write)$|"
    r"(^|\.)(glob|rglob|iterdir)$|^os\.(walk|listdir|scandir)$|^shutil\.|"
    r"^subprocess\.|(^|\.)time\.sleep$")
HANDED_OVER = ("to_thread", "run_in_executor", "run_io", "run_in_threadpool")


def blocking_calls(fn: ast.AsyncFunctionDef) -> list:
    """(line, call) of each blocking call made directly in `fn`'s own body."""
    out = []

    def visit(node, handed=False):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            here = handed
            if isinstance(ch, ast.Call):
                name = ast.unparse(ch.func)
                if any(h in name for h in HANDED_OVER):
                    here = True
                elif not handed and BLOCKING.search(name):
                    out.append((ch.lineno, name))
            visit(ch, here)
    visit(fn)
    return out


def audit(server_dir: Path = SERVER) -> dict:
    """{module file name: [(line, function, call), ...]} for every module with at least one."""
    found = {}
    for f in sorted(server_dir.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = f.relative_to(server_dir).as_posix()
        for n in ast.walk(tree):
            if isinstance(n, ast.AsyncFunctionDef):
                for line, call in blocking_calls(n):
                    found.setdefault(rel, []).append((line, n.name, call))
    return found


def counts(found: dict) -> dict:
    return {k: len(v) for k, v in sorted(found.items())}


def main(argv) -> int:
    found = audit()
    only = [a for a in argv if not a.startswith("-")]
    verbose = "-v" in argv
    total = 0
    for mod, sites in sorted(found.items(), key=lambda kv: -len(kv[1])):
        if only and mod not in only:
            continue
        total += len(sites)
        print(f"{len(sites):5d}  {mod}")
        if verbose:
            for line, fn, call in sites:
                print(f"         {mod}:{line} {fn}: {call}")
    print(f"{total:5d}  total")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
