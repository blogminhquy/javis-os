"""Test engine Claude Agent SDK (v0.9.35). Chạy tay / CI:

    python tests/run.py sdk_engine

KHÔNG cần Claude CLI hay đăng nhập - chỉ test phần thuần logic:
- factory claude_engine chọn đúng engine theo env JAVIS_CLAUDE_ENGINE (mặc định cli).
- map_message: message SDK → event dict đúng 'hợp đồng ClaudeCLI' (text/tool_call/
  tool_result/final + session_id/token/cost).
- _permission_gate: whitelist per-call allow/deny + pattern fnmatch + ghi audit JSONL.
(Chạy THẬT end-to-end với CLI + auth nằm ở smoke test tay, không thuộc CI.)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-sdktest-"))

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Factory: engine Claude LUÔN là SDK (nhánh Popen ClaudeCLI đã gỡ v0.9.37) ----
os.environ.pop("JAVIS_CLAUDE_ENGINE", None)
import claude_cli                                         # noqa: E402
from claude_cli import claude_engine                      # noqa: E402
import claude_sdk_engine                                  # noqa: E402
from claude_sdk_engine import ClaudeSDK, map_message      # noqa: E402

eng = claude_engine(system_prompt="x", cwd=".", tag="t", allowed_tools=["Read"], model="haiku")
check("factory: mặc định → ClaudeSDK", isinstance(eng, ClaudeSDK))
check("factory: truyền đủ tham số", eng.system_prompt == "x" and eng.allowed_tools == ["Read"]
      and eng.model == "haiku" and eng.tag == "t")
os.environ["JAVIS_CLAUDE_ENGINE"] = "cli"
check("factory: env=cli (đã gỡ) → vẫn ClaudeSDK", isinstance(claude_engine(), ClaudeSDK))
os.environ["JAVIS_CLAUDE_ENGINE"] = "sdk-loops"
check("factory: env=sdk-loops (đã gỡ) → vẫn ClaudeSDK", isinstance(claude_engine(tag="chat:abc12"), ClaudeSDK))
check("factory: class ClaudeCLI đã bị xoá hẳn", not hasattr(claude_cli, "ClaudeCLI"))
os.environ.pop("JAVIS_CLAUDE_ENGINE", None)

# ---- 2. map_message: parity hợp đồng event ----
from claude_agent_sdk import (AssistantMessage, UserMessage, SystemMessage, ResultMessage,  # noqa: E402
                              TextBlock, ToolUseBlock, ToolResultBlock)

evs, sid = map_message(SystemMessage(subtype="init", data={"session_id": "abc123"}))
check("map: init → bắt session_id, không event", evs == [] and sid == "abc123")

evs, sid = map_message(AssistantMessage(content=[
    TextBlock(text="xin chào"), TextBlock(text="   "),
    ToolUseBlock(id="t1", name="Read", input={"file_path": "a.md"})], model="claude"))
check("map: assistant → text + tool_call, bỏ text rỗng",
      evs == [{"type": "text", "content": "xin chào"},
              {"type": "tool_call", "name": "Read", "input": {"file_path": "a.md"}}])

evs, _ = map_message(UserMessage(content=[
    ToolResultBlock(tool_use_id="t1", content=[{"type": "text", "text": "nội dung file"}]),
    ToolResultBlock(tool_use_id="t2", content="chuỗi thẳng " + "x" * 600)]))
check("map: tool_result list + str, clip 500",
      evs[0] == {"type": "tool_result", "content": "nội dung file"}
      and evs[1]["content"].startswith("chuỗi thẳng") and len(evs[1]["content"]) == 500)

evs, sid = map_message(ResultMessage(
    subtype="success", duration_ms=1234, duration_api_ms=1000, is_error=False, num_turns=2,
    session_id="sess9", total_cost_usd=0.05, result="KQ",
    usage={"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 5,
           "output_tokens": 7}))
f = evs[0]
check("map: final đủ trường như ClaudeCLI",
      sid == "sess9" and f["type"] == "final" and f["content"] == "KQ"
      and f["session_id"] == "sess9" and f["cost_usd"] == 0.05 and f["duration_ms"] == 1234
      and f["tokens_in"] == 105 and f["tokens_out"] == 7)

evs, _ = map_message(UserMessage(content="chuỗi thuần không block"))
check("map: user content str → không event", evs == [])

evs, _ = map_message(ResultMessage(
    subtype="error_during_execution", duration_ms=1, duration_api_ms=1, is_error=True,
    num_turns=1, session_id="s2", result=None))
check("map: result LỖI + rỗng → error nói rõ lý do trước final",
      len(evs) == 2 and evs[0]["type"] == "error" and "error_during_execution" in evs[0]["content"]
      and evs[1]["type"] == "final" and evs[1]["content"] == "")

evs, _ = map_message(ResultMessage(
    subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
    num_turns=1, session_id="s3", result=""))
check("map: result rỗng nhưng KHÔNG lỗi → không thêm error", len(evs) == 1 and evs[0]["type"] == "final")

# ---- 3. _permission_gate: whitelist per-call + audit ----


async def gate_tests():
    e = ClaudeSDK(tag="loop-test", allowed_tools=["Read", "Glob", "mcp__javis__pos_*"])
    r1 = await e._permission_gate("Read", {}, None)
    r2 = await e._permission_gate("Write", {"file_path": "x"}, None)
    r3 = await e._permission_gate("mcp__javis__pos_order", {}, None)
    r4 = await e._permission_gate("Bash", {"command": "rm -rf"}, None)
    check("gate: tool trong whitelist → allow", r1.behavior == "allow")
    check("gate: tool ngoài whitelist → deny kèm lý do",
          r2.behavior == "deny" and "Write" in r2.message)
    check("gate: pattern mcp__javis__pos_* khớp", r3.behavior == "allow")
    check("gate: Bash bị chặn", r4.behavior == "deny")


asyncio.run(gate_tests())
audit = claude_sdk_engine._AUDIT_PATH
lines = [json.loads(x) for x in audit.read_text(encoding="utf-8").splitlines()] if audit.exists() else []
check("audit: ghi đủ 4 quyết định JSONL", len(lines) == 4
      and lines[0]["allowed"] is True and lines[1]["allowed"] is False
      and lines[1]["tool"] == "Write" and lines[0]["tag"] == "loop-test")


# ---- 3b. _permission_gate: pattern PREFIX kiểu Claude CLI (mcp__<server> = mọi tool của server) ----
# Bug thật ngoài đời: lane nền (kanban mcp-read, loop) nhận allow pattern "mcp__javis" từ
# mcp_hub.allow_patterns() theo ngữ nghĩa --allowedTools của Claude CLI, nhưng gate so bằng
# fnmatch nên "mcp__javis" KHÔNG khớp "mcp__javis__javis_search_tools" → mọi tool MCP nền bị
# từ chối ("user cancelled MCP tool call"), task báo connector hỏng dù connector sống.


async def gate_prefix_tests():
    e = ClaudeSDK(tag="loop-prefix", allowed_tools=["Read", "mcp__javis"])
    r1 = await e._permission_gate("mcp__javis__javis_search_tools", {}, None)
    r2 = await e._permission_gate("mcp__javis__pos_statistics", {}, None)
    r3 = await e._permission_gate("mcp__khac__tool_x", {}, None)
    r4 = await e._permission_gate("mcp__javisfake__tool_x", {}, None)
    check("gate: prefix mcp__javis khớp tool hub javis_search_tools", r1.behavior == "allow")
    check("gate: prefix mcp__javis khớp tool hub pos_statistics", r2.behavior == "allow")
    check("gate: prefix KHÔNG khớp server khác", r3.behavior == "deny")
    check("gate: prefix KHÔNG khớp server tên gần giống (javisfake)", r4.behavior == "deny")
    check("gate: deny tool MCP nói rõ connector KHÔNG hỏng (chống agent suy diễn OAuth chết)",
          r3.behavior == "deny" and "KHÔNG hỏng" in r3.message
          and "rào quyền phiên nền" in r3.message)


asyncio.run(gate_prefix_tests())

# ---- 4. Phase 3: plugin in-process + hub bỏ nhóm plugin ----
import plugins_host                                       # noqa: E402


async def _fake_call(args):
    return f"kq:{(args or {}).get('x', '')}"

_orig_pt, _orig_hooks = plugins_host.plugin_tools, plugins_host.has_tool_hooks
# chữ ký thật giờ có thêm keyword-only scope_vault (xem plugins_host.plugin_tools) -
# mock phải nhận được, không thì _plugins_server gọi kèm scope_vault=False sẽ vỡ TypeError.
plugins_host.plugin_tools = lambda mode, vr, *, scope_vault=True: (
    [{"fn": "vd_tool", "server": "javis", "name": "vd_tool", "description": "tool ví dụ",
      "schema": {"type": "object", "properties": {"x": {"type": "string"}}}}],
    {"vd_tool": {"call": _fake_call}})
plugins_host.has_tool_hooks = lambda vr: False
try:
    import tempfile as _tf
    from pathlib import Path as _P
    cfg = _P(_tf.mkdtemp(prefix="sdk-mcp-")) / "hub.json"
    cfg.write_text(json.dumps({"mcpServers": {"javis": {
        "type": "http", "url": "http://127.0.0.1:7777/hub/mcp",
        "headers": {"Authorization": "Bearer t", "X-Javis-Mode": "full"}}}}), encoding="utf-8")

    e = ClaudeSDK(tag="chat"); e.mcp_config = str(cfg); e.javis_mode = "full"
    servers, strict = e._mcp_servers()
    check("phase3: có javis-plugins in-process", "javis-plugins" in servers
          and servers["javis-plugins"].get("type") == "sdk")
    check("phase3: hub entry được gắn X-Javis-No-Plugins",
          servers["javis"]["headers"].get("X-Javis-No-Plugins") == "1")
    check("phase3: file config gốc KHÔNG bị sửa",
          "X-Javis-No-Plugins" not in cfg.read_text(encoding="utf-8"))

    g = ClaudeSDK(tag="loop", allowed_tools=["Read"]); g.mcp_config = str(cfg)
    gs, _ = g._mcp_servers()
    check("phase3: fork GATED không đấu plugin in-process (giữ cô lập)",
          "javis-plugins" not in (gs or {}))

    e2 = ClaudeSDK(tag="chat")   # không mcp_config (0 connection) → vẫn có plugin in-process
    s2, _ = e2._mcp_servers()
    check("phase3: không hub vẫn có plugin in-process", s2 and "javis-plugins" in s2)

    opts = e._options()
    check("phase3: chat nạp settings máy (parity CLI)",
          getattr(opts, "setting_sources", None) == ["user", "project", "local"])
    gopts = g._options()
    check("phase3: fork gated KHÔNG nạp settings máy (allow-rule không che gate)",
          getattr(gopts, "setting_sources", None) in (None, []))
finally:
    plugins_host.plugin_tools, plugins_host.has_tool_hooks = _orig_pt, _orig_hooks

# ---- 5. Watchdog ba trần: chờ TOOL ≠ treo, và chờ CHỮ ĐẦU cũng ≠ treo ----
# v0.9.41: tool chạy lâu hơn IDLE phải sống (trước đây bị chém oan).
# v0.9.277: thêm trần thứ ba cho khoảng im TRƯỚC chữ đầu tiên. Hội thoại dài thì lượt đầu
# phải nạp lại toàn bộ ngữ cảnh nên lâu, im lúc đó không phải treo - người dùng thật báo
# "chat dài là dính 'Claude không phản hồi 180s'". Im lặng SAU khi đã có chữ thì vẫn ngắt
# ở IDLE như cũ, nếu không thì mất luôn tác dụng chống treo.
import claude_agent_sdk  # noqa: E402


def _fake_client(messages_gen):
    class _Fake:
        def __init__(self, options=None): pass
        async def connect(self): pass
        async def query(self, prompt): pass
        async def interrupt(self): pass
        async def disconnect(self): pass
        def receive_response(self): return messages_gen()
    return _Fake


async def _run_query():
    e = ClaudeSDK(tag="wd-test")
    return [ev async for ev in e.query("x")]


def _rm(sid="s1", result="OK"):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                         num_turns=1, session_id=sid, result=result)


async def _gen_slow_tool():
    yield AssistantMessage(content=[ToolUseBlock(id="t1", name="Bash", input={})], model="m")
    await asyncio.sleep(0.8)   # tool chạy LÂU HƠN IDLE (0.3s) nhưng dưới TOOL_IDLE (10s)
    yield UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="xong")])
    yield _rm()


async def _gen_treo_giua():
    # ĐÃ có chữ rồi mới im: đây mới là treo thật → phải ngắt ở IDLE.
    yield AssistantMessage(content=[TextBlock(text="đang nghĩ...")], model="m")
    await asyncio.sleep(0.8)
    yield _rm(sid="s-treo-giua")


async def _gen_dau_lau_nhung_song():
    # Im LÂU HƠN IDLE trước chữ đầu (hội thoại dài nạp ngữ cảnh) nhưng dưới FIRST_IDLE
    # → phải SỐNG, về đích bình thường. Đây là ca người dùng thật bị chém oan.
    await asyncio.sleep(0.8)
    yield AssistantMessage(content=[TextBlock(text="xin lỗi để lâu")], model="m")
    yield _rm(sid="s-dau-lau")


async def _gen_treo_ngay_tu_dau():
    # Im quá cả FIRST_IDLE → vẫn phải ngắt, không được để treo vô hạn.
    await asyncio.sleep(3)
    yield _rm(sid="s-treo-dau")


os.environ["JAVIS_CLAUDE_IDLE_TIMEOUT"] = "0.3"
os.environ["JAVIS_CLAUDE_TOOL_TIMEOUT"] = "10"
os.environ["JAVIS_CLAUDE_FIRST_TIMEOUT"] = "1.5"
_orig_client_cls = claude_agent_sdk.ClaudeSDKClient
_orig_avail = ClaudeSDK.is_available
ClaudeSDK.is_available = lambda self: True
try:
    claude_agent_sdk.ClaudeSDKClient = _fake_client(_gen_slow_tool)
    evs = asyncio.run(_run_query())
    types = [e["type"] for e in evs]
    check("watchdog: tool chạy lâu hơn IDLE → KHÔNG bị chém oan, về đích final",
          "error" not in types and "final" in types and "tool_result" in types)

    claude_agent_sdk.ClaudeSDKClient = _fake_client(_gen_treo_giua)
    evs = asyncio.run(_run_query())
    errs = [e for e in evs if e["type"] == "error"]
    check("watchdog: ĐÃ có chữ rồi mới im → vẫn ngắt ở IDLE (giữ nguyên tác dụng chống treo)",
          len(errs) == 1 and "rồi im" in errs[0]["content"])

    claude_agent_sdk.ClaudeSDKClient = _fake_client(_gen_dau_lau_nhung_song)
    evs = asyncio.run(_run_query())
    types = [e["type"] for e in evs]
    check("watchdog: chờ chữ đầu lâu hơn IDLE nhưng dưới FIRST → KHÔNG chém oan (vụ chat dài)",
          "error" not in types and "final" in types)

    claude_agent_sdk.ClaudeSDKClient = _fake_client(_gen_treo_ngay_tu_dau)
    evs = asyncio.run(_run_query())
    errs = [e for e in evs if e["type"] == "error"]
    check("watchdog: im quá cả FIRST → vẫn ngắt, không để treo vô hạn",
          len(errs) == 1 and "chưa trả lời gì" in errs[0]["content"])
    check("watchdog: thông báo chờ-chữ-đầu mách người dùng mở hội thoại mới",
          errs and "Mở hội thoại mới" in errs[0]["content"])
finally:
    claude_agent_sdk.ClaudeSDKClient = _orig_client_cls
    ClaudeSDK.is_available = _orig_avail
    os.environ.pop("JAVIS_CLAUDE_IDLE_TIMEOUT", None)
    os.environ.pop("JAVIS_CLAUDE_TOOL_TIMEOUT", None)
    os.environ.pop("JAVIS_CLAUDE_FIRST_TIMEOUT", None)

# ---- 6. System prompt DÀI đẩy qua FILE, không nhét vào argv (lỗi CLINotFound trên Windows) ----
# Gốc lỗi: SDK để --append-system-prompt <prompt> trên dòng lệnh; > 32767 ký tự thì Windows
# CreateProcess chết -> FileNotFoundError bị dán nhãn "Claude Code not found at ...\\_bundled\\claude.exe".
from pathlib import Path as _Path6  # noqa: E402

_big = "Bạn là Javis.\n" + ("- một dòng hướng dẫn dài để độn kích thước prompt. " * 900)
_e6 = ClaudeSDK(system_prompt=_big, tag="t6")
_opts6 = _e6._options()
_ea6 = getattr(_opts6, "extra_args", None) or {}
_pf6 = _ea6.get("append-system-prompt-file")
check("options: prompt dài → dùng --append-system-prompt-file (đọc từ file)", bool(_pf6))
check("options: system_prompt preset KHÔNG kèm append inline (không lên argv)",
      isinstance(_opts6.system_prompt, dict) and "append" not in _opts6.system_prompt)
check("options: file tạm chứa ĐÚNG nội dung system prompt",
      bool(_pf6) and _Path6(_pf6).read_text(encoding="utf-8") == _big)
check("options: prompt dài vượt trần dòng lệnh Windows (chứng minh vì sao phải qua file)",
      len(_big) > 32767)
_e6._cleanup_tmp()
check("options: dọn file tạm sau khi xong", bool(_pf6) and not _Path6(_pf6).exists())

# SDK không có extra_args (bản cũ) → fallback nhét inline, vẫn chạy (chỉ hợp prompt ngắn)
import claude_agent_sdk as _casdk6  # noqa: E402
if "extra_args" not in getattr(_casdk6.ClaudeAgentOptions, "__dataclass_fields__", {}):
    _e6b = ClaudeSDK(system_prompt="ngắn", tag="t6b")
    _o6b = _e6b._options()
    check("options(SDK cũ): fallback append inline", _o6b.system_prompt.get("append") == "ngắn")

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_sdk_engine: tất cả pass")
