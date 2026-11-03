"""Two Windows bugs from issue #898 (a Windows Server 2022 install), checked on any OS.

    python tests/run.py windows_898      (no network)

Item 2: an npx MCP connector whose argument has a space (`--user-data-dir "C:\\My Javis\\x"`) died with
"'C:\\Program' is not recognized". npx is npx.cmd, run as `cmd.exe /c "C:\\Program Files\\nodejs\\npx.cmd" ...`,
and cmd strips the first and last quote of that line. Javis now runs `node npx-cli.js` of the same Node
install directly (as zalo_cli already did), so cmd.exe never parses the arguments.

Item 3: models write Windows paths URL style, `/C:/Users/...`. Neither pathlib reads that as drive C, so a
link to a real file in the brain was reported as "not found". The leading slash is now dropped first.
Simulated on Linux: a relative brain path `C:/brain` resolves under the current directory, exactly as
`C:/brain` does on Windows, so the drive-letter branch runs for real.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-win898-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def touch(p: Path, exe=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    if exe:
        p.chmod(p.stat().st_mode | stat.S_IXUSR)


# ---- item 2: npx.cmd runs through node, not cmd.exe ----
NODEJS = SCRATCH / "Program Files" / "nodejs"
touch(NODEJS / "npx.cmd", exe=True)
touch(NODEJS / "node.exe", exe=True)
touch(NODEJS / "node_modules" / "npm" / "bin" / "npx-cli.js")
ARGS = ["-y", "@playwright/mcp@latest", "--user-data-dir", r"C:\My Javis\profile"]

direct = mcp_client.npx_node_argv(str(NODEJS / "npx.cmd"))
check("npx.cmd maps to node.exe + npx-cli.js of the same install",
      direct == [str(NODEJS / "node.exe"), str(NODEJS / "node_modules" / "npm" / "bin" / "npx-cli.js")], direct)
check("not npx: no mapping", mcp_client.npx_node_argv(str(NODEJS / "other.cmd")) is None)
check("plain executable: no mapping", mcp_client.npx_node_argv("/usr/bin/npx") is None)

sess = mcp_client.McpStdioSession.__new__(mcp_client.McpStdioSession)
sess.command, sess.args = str(NODEJS / "npx.cmd"), list(ARGS)
argv = sess._argv()
check("session argv skips cmd.exe for npx.cmd", argv[0] != "cmd.exe" and argv[:2] == direct, argv)
check("arguments with spaces pass through as one item", argv[2:] == ARGS, argv)

# No npm CLI next to node: fall back to the old cmd.exe route instead of guessing.
LONE = SCRATCH / "lone"
touch(LONE / "npx.cmd", exe=True)
_which = mcp_client.shutil.which
mcp_client.shutil.which = lambda name, path=None: (str(LONE / "npx.cmd") if name.endswith("npx.cmd") else None)
try:
    sess.command = str(LONE / "npx.cmd")
    argv2 = sess._argv()
finally:
    mcp_client.shutil.which = _which
check("missing npm CLI keeps the cmd.exe route", argv2[:3] == ["cmd.exe", "/c", str(LONE / "npx.cmd")], argv2)

# ---- item 3: /C:/... links ----
os.chdir(SCRATCH)
BRAIN = "C:/brain"
touch(SCRATCH / "C:" / "brain" / "wiki" / "bao-cao.md")

check("helper drops the slash before a drive letter",
      main._bo_gach_truoc_o_dia("/C:/brain/x.md") == "C:/brain/x.md"
      and main._bo_gach_truoc_o_dia("\\C:\\brain\\x.md") == "C:\\brain\\x.md")
check("helper leaves POSIX and relative paths alone",
      main._bo_gach_truoc_o_dia("/home/a/x.md") == "/home/a/x.md"
      and main._bo_gach_truoc_o_dia("wiki/x.md") == "wiki/x.md"
      and main._bo_gach_truoc_o_dia("/Cx:/y") == "/Cx:/y")

check("markdown link /C:/... inside the brain becomes relative",
      main._link_muc_tieu_moi(BRAIN, "/C:/brain/wiki/bao-cao.md") == "wiki/bao-cao.md",
      main._link_muc_tieu_moi(BRAIN, "/C:/brain/wiki/bao-cao.md"))
check("same result as the C:/ form", main._link_muc_tieu_moi(BRAIN, "C:/brain/wiki/bao-cao.md") == "wiki/bao-cao.md")
check("a real /C:/ link is not reported missing",
      main._link_file_khong_thay(BRAIN, "Xem [báo cáo](/C:/brain/wiki/bao-cao.md).") == [])
check("a /C:/ link to a file that does not exist is still reported",
      main._link_file_khong_thay(BRAIN, "Xem [x](/C:/brain/wiki/khong-co.md).") == ["/C:/brain/wiki/khong-co.md"])

out = main._chuan_hoa_link_file(BRAIN, "File ở /C:/brain/wiki/bao-cao.md nhé.")
check("bare /C:/ path in the brain becomes a clickable relative path", out == "File ở `wiki/bao-cao.md` nhé.", out)
out2 = main._chuan_hoa_link_file(BRAIN, "[x](/C:/brain/wiki/bao-cao.md) và `/C:/brain/wiki/bao-cao.md`")
check("link and backtick forms are rewritten too", out2 == "[x](wiki/bao-cao.md) và `wiki/bao-cao.md`", out2)
out3 = main._chuan_hoa_link_file(BRAIN, "Ngoài brain: /C:/Windows/system.ini")
check("a /C:/ path outside the brain is left as written", out3 == "Ngoài brain: /C:/Windows/system.ini", out3)
out4 = main._chuan_hoa_link_file(BRAIN, "file:/C:/brain/wiki/bao-cao.md")
check("file:/C:/ keeps going through the file URI branch", out4 == "`wiki/bao-cao.md`", out4)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
