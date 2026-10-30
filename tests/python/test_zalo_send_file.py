"""Sending FILES on Zalo goes through the MCP tool `zalo_send_file`, not the one-shot CLI (server/zalo_cli.py `send_files`).

    python tests/run.py zalo_send_file      (no network, no real Zalo, no npx)

Incident 2026-10-14: Javis had to send an 11 KB Excel list to a staff member. `msg send-file` hung twice until it was killed at
120 seconds and the file never arrived, while PNG images through the same path went fine. Cause, read in zca-js 2.2.0
(`apis/uploadAttachment.js`, `apis/listen.js`): a file that is not an image is only confirmed (`file_done`) over the live
WebSocket, and the one-shot CLI never opens one, so zca-js waits forever. Opening one there would evict the MCP listener of the
inbox (it exits on a duplicate connection). So files go through the MCP process that already holds the connection.

What is checked here:
  1. Which files need that path (anything but jpg/png/webp/gif) and where the outbox is.
  2. send_files copies into a private subfolder of the session outbox, calls the right tool with the right arguments, and
     removes the subfolder afterwards, success or not.
  3. Every failure comes back as a sentence a person understands: older MCP without the tool, Zalo did not confirm, the MCP
     call itself timed out (marked so callers never resend), connection gone, odd result.
  4. The three pins of javis-zalo agree, and the catalog lists the new tool as dangerous (it sends).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_cli as Z  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. Which files, which folder
# ============================================================
check("images and GIFs keep the CLI path (their URL comes back over HTTP)",
      not any(Z.needs_live_confirm(p) for p in ["a.jpg", "b.JPEG", "c.png", "d.webp", "e.gif"]))
check("CANARY: xlsx, pdf, docx, zip, mp4, bmp and no extension need the live connection",
      all(Z.needs_live_confirm(p) for p in ["Danh sach.xlsx", "r.pdf", "d.docx", "z.zip", "v.mp4", "x.bmp", "noext"]))
check("outbox is ~/.zalo-agent-cli/outbox of the session (same as OUTBOX_DIR in javis-zalo)",
      Z.outbox_dir("/data/zalo/home").as_posix() == "/data/zalo/home/.zalo-agent-cli/outbox", Z.outbox_dir("/data/zalo/home"))

# ============================================================
# 2. send_files: copy, call, clean up
# ============================================================
HOME = Path(tempfile.mkdtemp(prefix="zsf-home-"))
SRC = Path(tempfile.mkdtemp(prefix="zsf-src-"))
(SRC / "Danh sach.xlsx").write_bytes(b"PK" + b"x" * 11000)
(SRC / "sub").mkdir()
(SRC / "sub" / "Danh sach.xlsx").write_bytes(b"other")

CALLS = []
CONN = {"id": "z1", "label": "Toán Thầy Thành", "env": {"HOME": str(HOME)}}
seen_during_call = {}
reply = {"value": None, "raise": None}


async def fake_goi(conn, tool, args):
    CALLS.append((conn, tool, args))
    seen_during_call["files"] = {p: Path(p).read_bytes() for p in args["paths"]}
    if reply["raise"]:
        raise reply["raise"]
    return reply["value"]


fake_channel = types.ModuleType("zalo_personal_channel")
fake_channel.ket_noi_theo_id = lambda cid: CONN if cid == "z1" else None
fake_channel._goi = fake_goi
sys.modules["zalo_personal_channel"] = fake_channel


def send(files, **kw):
    return asyncio.run(Z.send_files(kw.pop("conn_id", "z1"), str(HOME), "8899", files, **kw))


reply["value"] = {"success": True, "sent": 1, "files": ["Danh sach.xlsx"], "messageIds": ["123"]}
ok, data, err = send([SRC / "Danh sach.xlsx"], thread_type=0, caption="Gửi chị Hằng danh sách")
conn, tool, args = CALLS[-1]
check("success: ok, the MCP result, no error", ok is True and data["messageIds"] == ["123"] and err == "", (ok, data, err))
check("calls zalo_send_file on that connection", tool == "zalo_send_file" and conn is CONN, (tool, conn))
check("passes threadId, threadType, caption", args["threadId"] == "8899" and args["threadType"] == 0
      and args["caption"] == "Gửi chị Hằng danh sách", args)
outbox = Z.outbox_dir(str(HOME)).resolve()
check("CANARY: paths given to the tool sit inside the session outbox (the tool refuses anything else)",
      all(Path(p).resolve().parent.parent == outbox for p in args["paths"]), args["paths"])
check("the file reached the outbox whole, with its own name",
      list(seen_during_call["files"].values()) == [(SRC / "Danh sach.xlsx").read_bytes()]
      and Path(args["paths"][0]).name == "Danh sach.xlsx", list(seen_during_call["files"]))
check("the per-send subfolder is gone afterwards", list(outbox.iterdir()) == [], list(outbox.iterdir()))

ok, data, err = send([SRC / "Danh sach.xlsx", SRC / "sub" / "Danh sach.xlsx"], thread_type=1)
names = [Path(p).name for p in CALLS[-1][2]["paths"]]
check("two files with one name: both go, the second renamed (no overwrite)",
      names == ["Danh sach.xlsx", "Danh sach (2).xlsx"] and set(seen_during_call["files"].values()) == {
          (SRC / "Danh sach.xlsx").read_bytes(), b"other"}, names)
check("group thread type passes through", CALLS[-1][2]["threadType"] == 1)

# ============================================================
# 3. Failures as sentences
# ============================================================
reply["value"] = None
reply["raise"] = RuntimeError("Error: Zalo did not confirm the upload of Danh sach.xlsx within 60s. Nothing was sent.")
ok, data, err = send([SRC / "Danh sach.xlsx"])
check("Zalo did not confirm: failure with the reason, without the 'Error:' prefix",
      ok is False and err.startswith("Zalo did not confirm") and "Nothing was sent" in err, err)
check("that is NOT a call timeout (nothing was sent, so a retry is safe)", not Z.is_timeout(err))
check("CANARY: outbox cleaned up after a failure too", list(outbox.iterdir()) == [], list(outbox.iterdir()))

reply["raise"] = RuntimeError("MCP error -32602: Tool zalo_send_file not found")
ok, data, err = send([SRC / "Danh sach.xlsx"])
check("older javis-zalo without the tool: says to update Javis and restart the connection, no QR",
      ok is False and "bản javis-zalo cũ" in err and "Cập nhật Javis" in err, err)

reply["raise"] = TimeoutError("tool không phản hồi sau 120s")
ok, data, err = send([SRC / "Danh sach.xlsx"])
check("the MCP call itself timed out: marked as a timeout (the file may have gone, callers must not resend)",
      ok is False and Z.is_timeout(err), err)

reply["raise"] = None
reply["value"] = {"text": "???"}
ok, data, err = send([SRC / "Danh sach.xlsx"])
check("odd result is a failure, not a silent 'sent'", ok is False and "lạ" in err, err)

n = len(CALLS)
ok, data, err = send([SRC / "Danh sach.xlsx"], conn_id="gone")
check("connection no longer on: failure, MCP not called", ok is False and "z1" not in err and "gone" in err and len(CALLS) == n, err)

ok, data, err = send([SRC / "missing.pdf"])
check("unreadable source: failure before calling MCP, outbox clean",
      ok is False and "hộp gửi" in err and len(CALLS) == n and list(outbox.iterdir()) == [], err)

# ============================================================
# 4. Pins and catalog
# ============================================================
import zalo_login  # noqa: E402

cat = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))


def find_zalo(o):
    """The Zalo connector entry, wherever the catalog nests it."""
    if isinstance(o, dict):
        if o.get("id") == "zalo" and "args" in o:
            return o
        o = list(o.values())
    for v in o if isinstance(o, list) else []:
        r = find_zalo(v)
        if r:
            return r
    return None


zalo = find_zalo(cat)
# 0.183.0: v1.5.0 (history kept across restarts, `sync` coverage on reads); still has zalo_send_file from v1.4.0.
# 0.282.0: v1.6.1 (zalo_get_labels, the chat tags the bot reads; tools call the live API after a re-login).
# 0.334.0: v1.7.0 (emoji reactions in the live feed, zalo_add_reaction, cliMsgId on every message).
# 0.346.0: v1.8.0 (group note-list, note-edit keeps the pin: the Store tools zalo_list_notes / zalo_edit_note).
# 0.414.0: v1.9.0 (zalo_send_typing for "đang soạn tin", styles on zalo_send_message).
check("CANARY: the three javis-zalo pins agree and are v1.4.0 or later (the first with zalo_send_file)",
      Z.CLI_PACKAGE == zalo_login._CLI_PACKAGE and Z.CLI_PACKAGE in zalo["args"] and Z.CLI_PACKAGE.endswith("/v1.9.0"),
      (Z.CLI_PACKAGE, zalo_login._CLI_PACKAGE, zalo["args"]))
check("the previous pins are listed as old commands, so existing connections move to the new one",
      all(Z.CLI_PACKAGE.replace("v1.9.0", v) in [a for c in zalo["lenh_cu"] for a in (c.get("args") or [])]
          for v in ("v1.3.0", "v1.4.0", "v1.5.0", "v1.6.0", "v1.6.1", "v1.7.0", "v1.8.0")))
check("zalo_send_file is in the danger group (it sends, like zalo_send_message)",
      "zalo_send_file" in zalo["tool_meta"]["danger"] and "zalo_send_message" in zalo["tool_meta"]["danger"])
check("zalo_add_reaction is in the danger group too: the contact sees the reaction",
      "zalo_add_reaction" in zalo["tool_meta"]["danger"])
check("zalo_send_typing is in the danger group: the contact sees \"typing\" (0.414.0)",
      "zalo_send_typing" in zalo["tool_meta"]["danger"])

check("no em dash in this file or zalo_cli.py", chr(0x2014) not in open(__file__, encoding="utf-8").read()
      and chr(0x2014) not in (SERVER / "zalo_cli.py").read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_zalo_send_file: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_zalo_send_file: tất cả pass")
