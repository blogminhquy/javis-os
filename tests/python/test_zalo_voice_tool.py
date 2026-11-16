"""zalo_voice_tool: the zalo_send_voice MCP tool is added once to a known javis-zalo copy, and to nothing else."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

import zalo_voice_tool as Z  # noqa: E402

SAMPLE = '''import { z } from "zod";
import { OUTBOX_DIR } from "../core/send-files.js";
export function registerTools(server, api) {
    const live = () => api;
    // --- zalo_send_file ---
    server.registerTool("zalo_send_file", {}, async () => {});
}
'''

fails = 0


def check(name, cond):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails += 1


out = Z.patch_text(SAMPLE)
check("tool added", Z.MARK in out and "sendVoice" in out)
check("filesInside imported", 'import { OUTBOX_DIR, filesInside }' in out)
check("tool sits before zalo_send_file", out.index("zalo_send_voice") < out.index("// --- zalo_send_file ---"))
check("second pass changes nothing", Z.patch_text(out) == "")
check("unknown file left alone", Z.patch_text("console.log('x')") == "")

with tempfile.TemporaryDirectory() as tmp:
    mcp = Path(tmp) / "connector-home" / "zalo-a" / ".npm" / "_npx" / "abc" / "node_modules" / "javis-zalo" / "src" / "mcp"
    mcp.mkdir(parents=True)
    (mcp / "mcp-tools.js").write_text(SAMPLE, encoding="utf-8")
    brain = Path(tmp) / "brains" / "x" / "node_modules" / "javis-zalo" / "src" / "mcp"
    brain.mkdir(parents=True)
    (brain / "mcp-tools.js").write_text(SAMPLE, encoding="utf-8")
    changed = Z.ensure(tmp)
    check("hidden npx copy patched", len(changed) == 1 and Z.MARK in (mcp / "mcp-tools.js").read_text(encoding="utf-8"))
    check("brains never walked", Z.MARK not in (brain / "mcp-tools.js").read_text(encoding="utf-8"))
    check("ensure is idempotent", Z.ensure(tmp) == [])

sys.exit(1 if fails else 0)
