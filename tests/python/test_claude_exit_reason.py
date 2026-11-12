"""A `claude` that exits before answering names the reason it printed (customer report, 2026-11-12).

    python tests/run.py claude_exit_reason

claude-agent-sdk raises ProcessError("Command failed with exit code 1", stderr="Check stderr output for details")
when the process dies before a result; that second string is a placeholder, the real stderr goes to the engine's
callback. The chat showed the placeholder. No Claude CLI or sign-in needed here: the SDK client is faked. The four
stderr lines below were measured on Claude Code 2.1.322 with SDK 0.2.172.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-exitreason-"))

import claude_agent_sdk  # noqa: E402
import claude_exit_reason as xr  # noqa: E402
import claude_sdk_engine  # noqa: E402
import claude_warm  # noqa: E402
import localefmt  # noqa: E402
from claude_cli import claude_engine  # noqa: E402
from claude_sdk_engine import ClaudeSDK  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


BARE = "SDK engine: ProcessError: Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for details"
ROOT_LINE = "--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons"
MCP_LINES = ["Error: Invalid MCP configuration:", "MCP config file not found: /x/mcp.json"]
FLAG_LINE = "error: unknown option '--effort'"
SETTINGS_LINE = 'Error: Settings file not found: /tmp/x/{"fastMode": fal'


def both(stderr, text=BARE):
    out = []
    for lang in ("vi", "en"):
        tok = localefmt.dat_ngon_ngu_yeu_cau(lang)
        try:
            out.append(xr.explain(text, stderr))
        finally:
            localefmt.bo_ngon_ngu_yeu_cau(tok)
    return out


# ---- 1. explain: which errors it takes, and what it says ----
check("an error that is not the bare exit code is left alone",
      xr.explain("SDK engine: ValueError: abc", [ROOT_LINE]) is None and xr.explain("", ()) is None
      and xr.explain(None, ()) is None)
check("an exit code that already carries its reason (SDK 0.2.17x ResultError) is left alone",
      xr.explain("SDK engine: ResultError: Claude Code returned an error result: Error: --resume requires a valid "
                 "session ID (exit code: 1)", ["x"]) is None)

vi, en = both([ROOT_LINE])
check("root: says Javis runs as root, first thing", vi.startswith("Claude Code từ chối chạy vì Javis đang chạy bằng "
                                                                   "tài khoản root") and "runs as root" in en[:70])
check("root: names both ways out", "IS_SANDBOX=1" in vi and "tài khoản thường" in vi
      and "IS_SANDBOX=1" in en and "regular user" in en)
check("root: still quotes what claude printed", ROOT_LINE in vi and ROOT_LINE in en)

vi, en = both(MCP_LINES)
check("bad MCP config: points at the Connections page", "trang Kết nối" in vi and "Connections page" in en)
check("bad MCP config: quotes both lines, joined", "Error: Invalid MCP configuration: | MCP config file not found" in vi)

vi, en = both([FLAG_LINE])
check("unknown option: says to update Claude Code", "claude update" in vi and "claude update" in en
      and FLAG_LINE in vi)

vi, en = both([SETTINGS_LINE])
check("any other reason: exit code plus the quoted line, braces intact",
      vi.startswith("Claude Code dừng với mã thoát 1 trước khi trả lời.") and SETTINGS_LINE in vi
      and en.startswith("Claude Code stopped with exit code 1 before answering.") and SETTINGS_LINE in en)

vi, en = both([])
check("nothing printed: says so and says where to look", "không in ra lý do" in vi and "printed no reason" in en)
check("the SDK placeholder never reaches the user",
      all("Check stderr" not in s and "SDK engine" not in s for s in both([]) + both([ROOT_LINE]) + both(MCP_LINES)))

vi, _ = both(["x"], "SDK engine: ProcessError: Command failed with exit code -9 (exit code: -9)\n"
                    "Error output: Check stderr output for details")
check("a signal exit keeps its own code", "mã thoát -9" in vi)

vi, _ = both([f"noise {i}" for i in range(10)] + ["  ", "last — line " + "y" * 400])
check("only the last three lines are quoted, each cut", "noise 7" not in vi and "noise 8 | noise 9 | last" in vi
      and len(vi) < 500)
for name, s in (("root", both([ROOT_LINE])), ("mcp", both(MCP_LINES)), ("flag", both([FLAG_LINE])),
                ("other", both(["a — b – c"])), ("none", both([]))):
    check(f"no long dash in the '{name}' message, quoted lines included",
          all("—" not in x and "–" not in x for x in s))

# ---- 2. rewrite: only the bare error event changes ----
ev = {"type": "error", "content": BARE, "error_type": "ProcessError", "status_code": None}
got = xr.rewrite(ev, [ROOT_LINE])
check("the error event keeps its other fields", got["error_type"] == "ProcessError" and "root" in got["content"]
      and ev["content"] == BARE)
check("text, final and tool events come back as they are",
      all(xr.rewrite(e, [ROOT_LINE]) is e for e in ({"type": "text", "content": BARE}, {"type": "final", "content": BARE},
                                                    {"type": "error", "content": "other"}, None, "x")))
lost = {"type": "error", "resume_failed": True, "content": BARE}
check("a lost thread is left to the callers that prime a new one", xr.rewrite(lost, ["x"]) is lost)


# ---- 3. the engine: every caller of ClaudeSDK.query gets it ----
def raising_client(exc):
    class _Fake:
        def __init__(self, options=None): pass
        async def connect(self): raise exc
        async def query(self, prompt): pass
        async def interrupt(self): pass
        async def disconnect(self): pass
        def receive_response(self): raise exc
    return _Fake


def with_stderr(engine, lines):
    original = engine._options

    def options():
        o = original()
        for line in lines:
            engine._on_stderr(line)
        return o
    engine._options = options
    return engine


async def events(stream):
    return [ev async for ev in stream]


EXC = Exception("Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for details")
_client, _avail = claude_agent_sdk.ClaudeSDKClient, ClaudeSDK.is_available
ClaudeSDK.is_available = lambda self: True
claude_agent_sdk.ClaudeSDKClient = raising_client(EXC)
try:
    eng = with_stderr(claude_engine(system_prompt="x", cwd=".", tag="exit-test"), [ROOT_LINE])
    check("claude_engine installs the wrapper, once", getattr(ClaudeSDK.query, "_javis_exit_reason", False)
          and xr.install() and not getattr(ClaudeSDK.query.__wrapped__, "_javis_exit_reason", False))
    evs = asyncio.run(events(eng.query("hi")))
    errs = [e["content"] for e in evs if e["type"] == "error"]
    check("ClaudeSDK.query: exit 1 as root names root, not the SDK placeholder",
          len(errs) == 1 and "root" in errs[0] and "Check stderr" not in errs[0], errs)

    eng = with_stderr(claude_engine(system_prompt="x", cwd=".", tag="exit-test"), MCP_LINES)
    evs = asyncio.run(events(claude_warm.cold_query(eng, "hi")))
    errs = [e["content"] for e in evs if e["type"] == "error"]
    check("cold_query (Telegram): the same", len(errs) == 1 and "MCP" in errs[0] and "Check stderr" not in errs[0], errs)

    eng = with_stderr(claude_engine(system_prompt="x", cwd=".", tag="chat"), [FLAG_LINE])
    evs = asyncio.run(events(claude_warm._query(eng, "hi", "conv-1", allow_warm=False)))
    errs = [e["content"] for e in evs if e["type"] == "error"]
    check("claude_warm._query (dashboard chat, its own loop): the same",
          len(errs) == 1 and "claude update" in errs[0] and "Check stderr" not in errs[0], errs)

    eng = with_stderr(claude_engine(system_prompt="x", cwd=".", tag="exit-test"),
                      ["No conversation found with session ID: 3f1c2a9e-0000-4000-8000-123456789abc"])
    eng.session_id = "3f1c2a9e-0000-4000-8000-123456789abc"
    evs = asyncio.run(events(claude_warm.cold_query(eng, "hi")))
    check("a lost thread by exit code is still flagged resume_failed (07/11/2026)",
          [e.get("resume_failed") for e in evs if e["type"] == "error"] == [True] and eng.session_id is None)

    claude_agent_sdk.ClaudeSDKClient = raising_client(ValueError("abc"))
    eng = with_stderr(claude_engine(system_prompt="x", cwd=".", tag="exit-test"), [ROOT_LINE])
    evs = asyncio.run(events(eng.query("hi")))
    check("an unrelated SDK error keeps its original text",
          [e["content"] for e in evs if e["type"] == "error"] == ["SDK engine: ValueError: abc"])
finally:
    claude_agent_sdk.ClaudeSDKClient, ClaudeSDK.is_available = _client, _avail

check("claude_cli installs it where every Claude engine is built",
      "claude_exit_reason.install()" in (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8"))

print("\n" + ("GREEN" if not _fails else f"RED: {len(_fails)} failed"))
raise SystemExit(1 if _fails else 0)
