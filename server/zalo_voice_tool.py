"""Give every installed javis-zalo a `zalo_send_voice` MCP tool (2026-11-16).

javis-zalo (pinned upstream) sends audio only as a file card. A voice message that plays in the chat needs the file
uploaded through the live connection, then `sendVoice` with the link Zalo returns. Until upstream ships that tool,
Javis adds it to each installed copy: the bundled one under `<state>/tools` and the npx copies each connection keeps
under `<state>/connector-home`. An update reinstalls those copies, so this runs at every start of the Zalo loop and
again whenever a send finds the tool missing. It is idempotent and leaves a copy it does not recognise untouched.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

MARK = "zalo_send_voice"
_IMPORT_OLD = 'import { OUTBOX_DIR } from "../core/send-files.js";'
_IMPORT_NEW = 'import { OUTBOX_DIR, filesInside } from "../core/send-files.js";'
_ANCHOR = "    // --- zalo_send_file ---"

TOOL_JS = '''    // --- zalo_send_voice (added by Javis, server/zalo_voice_tool.py) ---
    server.registerTool(
        "zalo_send_voice",
        {
            title: "Send Zalo Voice Message",
            description: "Send an audio file from the outbox folder as a Zalo VOICE message. threadType: 0=DM, 1=Group.",
            inputSchema: z.object({
                threadId: z.string(),
                path: z.string(),
                threadType: z.number().int().min(0).max(1).default(THREAD_USER),
            }),
        },
        async (args) => {
            try {
                const a = live();
                const [file] = filesInside([args.path], OUTBOX_DIR);
                const up = await Promise.race([
                    a.uploadAttachment([file], args.threadId, Number(args.threadType)),
                    new Promise((_, rej) => setTimeout(() => rej(new Error("Zalo did not confirm the upload in 60s")), 60000)),
                ]);
                const url = up?.[0]?.fileUrl;
                if (!url) throw new Error("Zalo gave no file link: " + JSON.stringify(up).slice(0, 200));
                const res = await a.sendVoice({ voiceUrl: url }, args.threadId, Number(args.threadType));
                return ok({ success: true, voiceUrl: url, result: res });
            } catch (e) {
                console.error("[mcp-tools] zalo_send_voice error:", e.message);
                return err(e.message);
            }
        },
    );

'''


def patch_text(src: str) -> str:
    """The file with the tool added, or "" when it already has it or does not look like a known mcp-tools.js."""
    if MARK in src or _IMPORT_OLD not in src or _ANCHOR not in src:
        return ""
    src = src.replace(_IMPORT_OLD, _IMPORT_NEW, 1)
    i = src.index(_ANCHOR)
    return src[:i] + TOOL_JS + src[i:]


def candidates(state_dir) -> List[Path]:
    """Every javis-zalo `src/mcp/mcp-tools.js` under `<state>/tools` and `<state>/connector-home` (hidden npx caches
    included; the rest of the state folder, brains above all, is never walked)."""
    out: List[Path] = []
    for top in (Path(state_dir) / "tools", Path(state_dir) / "connector-home"):
        if not top.is_dir():
            continue
        for d, _subs, files in os.walk(top):
            if "mcp-tools.js" in files and d.replace("\\", "/").endswith("node_modules/javis-zalo/src/mcp"):
                out.append(Path(d) / "mcp-tools.js")
    return out


def ensure(state_dir) -> List[str]:
    """Add the tool wherever it is missing. Returns the files changed; never raises."""
    changed: List[str] = []
    try:
        for f in candidates(state_dir):
            try:
                new = patch_text(f.read_text(encoding="utf-8"))
                if new:
                    f.write_text(new, encoding="utf-8")
                    changed.append(str(f))
            except OSError:
                continue
    except Exception:       # noqa: BLE001 - a failed patch only means voice goes as a file
        pass
    return changed
