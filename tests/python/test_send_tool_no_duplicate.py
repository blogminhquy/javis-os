"""A file a send tool already delivered mid-turn is not attached again at the end of the turn.

    python tests/run.py send_tool_no_duplicate      (no network)

15/11/2026: a Full-level Zalo bot sent a sales chart with zalo_send_image, then `collect_turn_files` picked the same
path out of the tool call's payload and sent it a second time.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context as cc  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


root = Path(tempfile.mkdtemp(prefix="javis-sendtool-"))
img = root / "attachments" / "chart.png"
img.parent.mkdir(parents=True)
t0 = time.time()
img.write_bytes(b"\x89PNG" + b"0" * 100)
payload = {"threadId": "g1", "filePath": str(img)}

for name in ("zalo_send_image", "mcp__zalo__zalo_send_image", "javis-plugins.zalo_send_file"):
    sent = cc.paths_sent_by_tool(name, payload, cwd=str(root))
    check(f"{name} marks its file as sent", os.path.normcase(os.path.normpath(str(img))) in sent, sent)
check("a send tool named inside a Codex item", bool(cc.paths_sent_by_tool(
    "", {"tool": "zalo_send_image", "arguments": json.dumps(payload)}, cwd=str(root))))
check("a relative path resolves against the brain",
      bool(cc.paths_sent_by_tool("zalo_send_image", {"filePath": "attachments/chart.png"}, cwd=str(root))))
check("CANARY: any other tool marks nothing", cc.paths_sent_by_tool("Write", {"file_path": str(img)}) == set())
check("a broken payload never raises", cc.paths_sent_by_tool("zalo_send_image", object()) == set())

written = cc.candidate_paths_from_tool(payload)
check("(setup) without the fix the end of the turn would attach it",
      cc.collect_turn_files("", written, t0, cwd=str(root)) != [])
sent = cc.paths_sent_by_tool("zalo_send_image", payload, cwd=str(root))
check("with it the file is not attached a second time",
      cc.collect_turn_files("", written, t0, cwd=str(root), exclude=sent) == [])

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("All green.")
