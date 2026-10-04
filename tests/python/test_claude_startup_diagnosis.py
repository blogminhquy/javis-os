"""A Claude Code startup timeout must say the real number and the real culprit (0.72.1).

    python tests/run.py claude_startup_diagnosis

No network, no engine spawn.

Field report (2026-10-03/04, a customer bot on a Zalo personal account): every reply died after
exactly 5 minutes with "Claude Code không khởi động xong trong trần cho phép ...". Two lies in
that message, both covered here:

  1. "trần cho phép" instead of "300s". `ap_tran_khoi_dong` writes the SDK env var itself on the
     first turn, so from the second turn it sees the var, assumes the USER set it and returns
     None, and the error text lost its number.
  2. "almost always a data source (MCP)" was a guess. Javis never looked at what `claude` printed
     and never recorded whether `claude` reached the hub at all, so the message could not tell
     "hub too slow" from "claude never got that far (login, network, update)".

The hub-side trace lives in `hub_trace`, the diagnosis in `claude_sdk_engine`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextlib
import io
import os
import re
import sys
import time

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


import claude_sdk_engine as eng  # noqa: E402
import hub_trace  # noqa: E402
import mcp_hub  # noqa: E402

TIMEOUT = Exception("Control request timeout: initialize")
# The dashboard card cuts last_error at 160 characters (dashboard/chatbots.js), so the verdict
# has to be inside that window or the owner never sees it.
UI_CUT = 160


def _clean_env():
    os.environ.pop("JAVIS_CLAUDE_INIT_TIMEOUT", None)
    os.environ.pop("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", None)


def hub(called=True, init_s=None, list_s=None, pending=None, pending_s=0.0):
    return {"called": called, "init_s": init_s, "list_s": list_s,
            "pending": pending, "pending_s": pending_s}


def diag(hub_summary=None, attached=True, stderr=None):
    return {"hub_attached": attached, "hub": hub_summary or hub(), "stderr": stderr or []}


# ============================================================
# 1. The number survives the second turn
# ============================================================
_clean_env()
first = eng.ap_tran_khoi_dong()
second = eng.ap_tran_khoi_dong()          # what the second chat turn really gets
check("first turn reports 300s", first == 300.0)
check("second turn returns None (env already there) - the trigger of the bug", second is None)
msg2 = eng.loi_de_hieu(TIMEOUT, second)
check("second turn error still names 300s", "300s" in msg2)
check("second turn error no longer says 'trần cho phép'", "trần cho phép" not in msg2)

_clean_env()
os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"] = "123000"   # the user set the SDK var themselves
check("a user-set SDK limit is named too (123s)",
      "123s" in eng.loi_de_hieu(TIMEOUT, eng.ap_tran_khoi_dong()))
_clean_env()
check("nothing known at all still reads fine, never 'None'",
      "None" not in eng.loi_de_hieu(TIMEOUT))


# ============================================================
# 2. hub_trace: did claude reach the hub, and how long did it take?
# ============================================================
t0 = time.time()
check("tools/call is not tracked", hub_trace.begin("tools/call") is None)
check("nothing recorded yet -> not called", hub_trace.since(t0)["called"] is False)

ev_init = hub_trace.begin("initialize")
hub_trace.end(ev_init)
ev_list = hub_trace.begin("tools/list")
s = hub_trace.since(t0)
check("initialize recorded with a duration", s["called"] and s["init_s"] is not None)
check("tools/list still running is reported as pending",
      s["list_s"] is None and s["pending"] == "tools/list")
hub_trace.end(ev_list)
s = hub_trace.since(t0)
check("finished tools/list gets its duration, nothing pending",
      s["list_s"] is not None and s["pending"] is None)
check("requests older than the turn start are ignored",
      hub_trace.since(time.time() + 1)["called"] is False)

# the real hub entry point feeds the trace
t1 = time.time()
asyncio.run(mcp_hub._handle_one_traced(
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, "full"))
check("mcp_hub records an initialize request", hub_trace.since(t1)["called"])
_hub_src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
_body = _hub_src.split("async def tra_loi_jsonrpc")[1].split("# ====")[0]
check("tra_loi_jsonrpc goes through the traced handler only",
      "_handle_one_traced(" in _body and "await _handle_one(" not in _body)


# ============================================================
# 3. The message states the culprit, verdict first
# ============================================================
m_never = eng.loi_de_hieu(TIMEOUT, 300.0, diag(hub(called=False)))
check("never reached the hub: says so inside the visible window",
      "chưa hề gọi" in m_never[:UI_CUT])
check("never reached the hub: does NOT send the owner to switch off MCP sources",
      "tắt nó đi" not in m_never and "trang Kết nối" not in m_never)
check("never reached the hub: points at the login (Models page)", "Models" in m_never)

m_slow = eng.loi_de_hieu(TIMEOUT, 300.0, diag(hub(init_s=0.1, list_s=140.0)))
check("hub answered after 140s: verdict in the visible window, with the number",
      "trả quá chậm" in m_slow[:UI_CUT] and "140s" in m_slow)
check("hub slow: the MCP advice (Connections page, Check) is back",
      "trang Kết nối" in m_slow and "JAVIS_CLAUDE_INIT_TIMEOUT" in m_slow)

m_pend = eng.loi_de_hieu(TIMEOUT, 300.0, diag(hub(init_s=0.1, pending="tools/list", pending_s=290.0)))
check("hub never answered: says it did not answer", "chưa trả lời" in m_pend[:UI_CUT])
check("hub never answered: MCP advice present", "trang Kết nối" in m_pend)

m_fast = eng.loi_de_hieu(TIMEOUT, 300.0, diag(hub(init_s=0.1, list_s=2.0)))
check("hub answered fast: says it is fine, with the number",
      "trả lời bình thường" in m_fast[:UI_CUT] and "2s" in m_fast)
check("hub answered fast: does NOT blame MCP sources", "trang Kết nối" not in m_fast)
check("hub answered fast: raising the limit is not suggested",
      "JAVIS_CLAUDE_INIT_TIMEOUT" not in m_fast)

m_none = eng.loi_de_hieu(TIMEOUT, 300.0, diag(attached=False))
check("no hub in this run: says so", "không đấu" in m_none[:UI_CUT])

m_err = eng.loi_de_hieu(TIMEOUT, 300.0, diag(hub(called=False),
                                             stderr=["x" * 500, "Error: not logged in"]))
check("what claude printed is shown", "Error: not logged in" in m_err)
check("an over-long stderr line is cut", "x" * 200 not in m_err)
check("the whole message stays short enough to read", len(m_err) < 800)

for ten, s in (("never", m_never), ("slow", m_slow), ("pending", m_pend), ("fast", m_fast),
               ("no hub", m_none), ("stderr", m_err)):
    check(f"'{ten}' message has no em/en dash", "\u2014" not in s and "\u2013" not in s)
    check(f"'{ten}' message no longer claims 'gần như luôn là do nguồn dữ liệu'",
          "Gần như luôn" not in s)

check("no diagnosis at all keeps the old generic hint (nothing to base a verdict on)",
      "trang Kết nối" in eng.loi_de_hieu(TIMEOUT, 300.0))


# ============================================================
# 4. Engine: collect stderr, build the diagnosis, hand it over
# ============================================================
e = eng.ClaudeSDK(tag="t")
buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    e._on_stderr("hello from claude\n")
check("stderr line is kept in the tail", e._stderr_tail[-1] == "hello from claude")
check("stderr line is still echoed to the server log", "hello from claude" in buf.getvalue())
for i in range(100):
    with contextlib.redirect_stderr(io.StringIO()):
        e._on_stderr(f"line {i}")
check("the tail is bounded", len(e._stderr_tail) <= 40)

e2 = eng.ClaudeSDK(tag="t")
t2 = time.time()
ev = hub_trace.begin("initialize")
hub_trace.end(ev)
e2._stderr_tail.append("boom")
d = e2._startup_diagnosis(t2)
check("diagnosis carries the hub summary", d["hub"]["called"] is True)
check("diagnosis carries the stderr tail", d["stderr"] == ["boom"])

_src = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
_query = _src.split("async def query")[1]
check("query() asks for the diagnosis only on the initialize timeout",
      "Control request timeout: initialize" in _query and "_startup_diagnosis(" in _query)
check("query() hands the diagnosis to loi_de_hieu",
      re.search(r"loi_de_hieu\(e, tran_init, \w+\)", _query) is not None)
check("query() writes the full detail to the server log",
      "[claude init timeout]" in _query)
check("options register the stderr collector",
      'kw["stderr"] = self._on_stderr' in _src)


if _fails:
    print(f"\nFAIL - test_claude_startup_diagnosis: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_claude_startup_diagnosis: tất cả pass")
