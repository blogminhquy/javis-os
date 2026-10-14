"""Resonance A5 trên nền main 0.107.0: engine THẬT của lượt làm và lượt review với SDK GIẢ, và kho phiên cũ nâng lên.

    python tests/run.py resonance_a5_engine_session_gate

Không gọi model, không cần Claude CLI hay đăng nhập. Kiểm hai chỗ main 0.107.0 (#623) đổi bên dưới A5 mà không đụng
file Cộng hưởng nào:

1. `claude_sdk_engine._mcp_servers`: phiên có `allowed_tools` giờ được nạp plugin tool khi danh sách nêu ĐÍCH DANH
   `mcp__javis-plugins__<tên>`. Lượt việc nền A5 dựng bằng `main._resonance_engine` (thư mục trống, MCP rỗng strict,
   `allowed_tools` là một tên canh gác không khớp công cụ nào, swap theo model việc nền, `strip_tools`,
   `pick_text_only_link`). Test dựng ĐÚNG đường đó cho system prompt của vai làm và vai review, thay
   `ClaudeSDKClient` bằng client giả để bắt `options` thật mà engine đưa cho SDK, rồi kiểm: không hub, không plugin,
   không công cụ native, cổng `can_use_tool` từ chối mọi lời gọi công cụ, không chuỗi dự phòng, không tự đổi
   provider. Ca đối chứng: một phiên nêu đích danh plugin tool THẬT thì có server plugin, chứng tỏ cách kiểm thấy
   được nếu A5 bị rò.
2. `sessions`: thêm bảng `cli_session_history` và ghi lịch sử trong `set_cli_session_id`. Kho phiên kiểu cũ (không
   có bảng đó) phải mở và nâng được, giữ nguyên dòng phiên của agent (kênh `agent:<slug>`, nguồn danh tính A5).
   CI chỉ fetch nông một commit nền, nên kho kiểu cũ được tạo bằng cách bỏ đúng bảng mới; đó là khác biệt schema
   duy nhất của #623 trong `sessions.py`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-a5-engine-")
os.environ["JAVIS_STATE_DIR"] = _STATE
Path(_STATE, "settings.json").write_text(json.dumps({
    "model": {"auxiliary": {"provider": "anthropic-cli", "model": "sonnet"},
              "main": {"provider": "anthropic-cli", "model": "sonnet"}},
    "setup_done": True}), encoding="utf-8")

import main  # noqa: E402
import aux_engine  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import sessions  # noqa: E402
import workflow_chat  # noqa: E402
import claude_agent_sdk  # noqa: E402
from claude_agent_sdk import PermissionResultDeny, ResultMessage  # noqa: E402
from claude_cli import claude_engine  # noqa: E402
from claude_sdk_engine import ClaudeSDK  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f" ({extra})" if extra and not cond else ""))
    if not cond:
        fails.append(name)


SENTINEL = "javis_reply_policy_khong_cong_cu"
captured = []


class FakeClient:
    """Thay ClaudeSDKClient: không mở tiến trình `claude`, chỉ ghi lại options rồi trả một kết quả chữ."""

    def __init__(self, options=None):
        captured.append(options)

    async def connect(self):
        pass

    async def query(self, prompt):
        pass

    async def interrupt(self):
        pass

    async def disconnect(self):
        pass

    def receive_response(self):
        async def gen():
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                                session_id="s-fake", result="BAN_CHU")
        return gen()


async def collect(eng, prompt="x"):
    return [ev async for ev in eng.query(prompt)]


_orig_client, _orig_avail = claude_agent_sdk.ClaudeSDKClient, ClaudeSDK.is_available
claude_agent_sdk.ClaudeSDKClient = FakeClient
ClaudeSDK.is_available = lambda self: True
try:
    # ---- 1. Engine của lượt làm và lượt review ----
    p_tools, _ = plugins_host.plugin_tools("full", None, scope_vault=False)
    plugin_names = sorted(t["fn"] for t in p_tools)
    check("có plugin tool thật trên máy test (nếu A5 bị rò thì thấy được)", bool(plugin_names))
    check("tên canh gác của A5 không cấp plugin tool nào", plugins_host.granted_plugin_tools([SENTINEL]) == set())

    roles = (("vai làm", "Bạn là trợ lý nguoi-lam-tom-tat. Soạn đúng bản được giao."), ("vai review", R.REVIEW_SYSTEM))
    for role, system_prompt in roles:
        eng, info = main._resonance_engine(system_prompt, "resonance")
        check(f"{role}: engine Claude SDK, không chuỗi dự phòng",
              isinstance(eng, ClaudeSDK) and not isinstance(eng, aux_engine._FallbackChain), type(eng).__name__)
        check(f"{role}: đúng provider và model đã chọn, chỉ chữ",
              info.get("requested_provider") == "anthropic-cli" and info.get("provider") == "anthropic-cli"
              and info.get("model") == "sonnet" and info.get("text_only") is True, json.dumps(info, ensure_ascii=False))
        if not isinstance(eng, ClaudeSDK):
            continue
        n0 = len(captured)
        evs = asyncio.run(collect(eng))
        check(f"{role}: lượt chạy qua SDK giả, trả chữ, không lỗi",
              len(captured) == n0 + 1 and any(e.get("type") == "final" and e.get("content") == "BAN_CHU" for e in evs)
              and not any(e.get("type") == "error" for e in evs), json.dumps(evs, ensure_ascii=False)[:300])
        opt = captured[-1]
        servers = getattr(opt, "mcp_servers", None)
        check(f"{role}: không hub, không plugin (MCP rỗng, strict)",
              isinstance(servers, dict) and not servers and getattr(opt, "strict_mcp_config", False) is True,
              repr(servers)[:200])
        check(f"{role}: chỉ tên canh gác trong allowed_tools, cổng từng lần gọi bật",
              list(opt.allowed_tools or []) == [SENTINEL] and opt.permission_mode == "default"
              and opt.can_use_tool is not None)
        check(f"{role}: không nạp settings máy người dùng", not getattr(opt, "setting_sources", None))
        check(f"{role}: công cụ native bị cấm sẵn",
              set(main.BOT_CAM_NATIVE) <= set(opt.disallowed_tools or []), repr(opt.disallowed_tools))
        probe = (["Bash", "Write", "Edit", "Read", "WebFetch", "WebSearch", "Task", "Skill", "NotebookEdit",
                  "mcp__javis__javis_goal", "mcp__javis__pos_order", f"mcp__javis-plugins__{plugin_names[0]}",
                  plugin_names[0], "mcp__javis-plugins"] if plugin_names else ["Bash"])
        denied = [n for n in probe if isinstance(asyncio.run(opt.can_use_tool(n, {}, None)), PermissionResultDeny)]
        check(f"{role}: cổng từ chối mọi lời gọi công cụ ({len(probe)} tên)", denied == probe,
              f"lọt: {sorted(set(probe) - set(denied))}")

    # Đối chứng: phiên nêu ĐÍCH DANH một plugin tool thật thì SDK mới (0.107.0) nạp server plugin cho nó.
    if plugin_names:
        ctl = claude_engine(system_prompt="x", cwd=_STATE, tag="a5-ctl",
                            allowed_tools=[f"mcp__{plugins_host.PLUGIN_SERVER}__{plugin_names[0]}"])
        ctl.mcp_config, ctl.mcp_strict = main._empty_mcp_file(), True
        asyncio.run(collect(ctl))
        check("đối chứng: nêu đích danh plugin thì có server plugin (cách kiểm thấy được rò rỉ)",
              plugins_host.PLUGIN_SERVER in (getattr(captured[-1], "mcp_servers", None) or {}))

    # Không tự đổi provider: model việc nền là provider chưa sẵn sàng thì swap lùi về Claude, A5 phải từ chối chạy.
    _orig_spec = aux_engine.read_spec
    aux_engine.read_spec = lambda settings=None: {"provider": "openrouter", "model": "khong/co-khoa"}
    try:
        eng, info = main._resonance_engine(R.REVIEW_SYSTEM, "resonance")
    finally:
        aux_engine.read_spec = _orig_spec
    check("provider đã chọn chưa sẵn sàng: không chạy thay bằng provider khác",
          eng is None and info.get("text_only") is False and info.get("requested_provider") == "openrouter",
          json.dumps(info, ensure_ascii=False))
finally:
    claude_agent_sdk.ClaudeSDKClient, ClaudeSDK.is_available = _orig_client, _orig_avail

# ---- 2. Kho phiên kiểu cũ nâng lên ----
db = Path(_STATE) / "sessions-old.db"
old = sessions.SessionStore(db_path=db)
sid = old.create_session(brain="Brain Default", engine="cli", title="Phiên agent cũ", channel="agent:nguoi-lam-tom-tat",
                         cli_session_id="cli-cu-1")
web = old.create_session(brain="Brain Default", channel="web", cli_session_id="cli-web-1")
with sqlite3.connect(db) as c:
    c.execute("DROP TABLE cli_session_history")      # đúng khác biệt schema của #623
    before = c.execute("SELECT id, brain, channel, cli_session_id, created_at FROM sessions ORDER BY id").fetchall()
    check("kho kiểu cũ: không có bảng cli_session_history",
          not c.execute("SELECT 1 FROM sqlite_master WHERE name='cli_session_history'").fetchone())
del old

new = sessions.SessionStore(db_path=db)
with sqlite3.connect(db) as c:
    has_table = bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='cli_session_history'").fetchone())
    after = c.execute("SELECT id, brain, channel, cli_session_id, created_at FROM sessions ORDER BY id").fetchall()
check("mã 0.107.0 mở kho cũ: tạo bảng mới", has_table)
check("dòng phiên cũ giữ nguyên (id, brain, kênh, phiên CLI, thời điểm tạo)", before == after and len(after) == 2)
row = new.get_session(sid) or {}
check("phiên agent cũ vẫn ra đúng danh tính agent (nguồn danh tính A5)",
      workflow_chat.persona_cua_phien(row) == ("agent", "nguoi-lam-tom-tat") and row.get("brain") == "Brain Default")
check("phiên web không thành phiên agent", workflow_chat.persona_cua_phien(new.get_session(web) or {}) is None)
new.set_cli_session_id(sid, "cli-moi-2")
with sqlite3.connect(db) as c:
    hist = c.execute("SELECT cli_session_id, session_id FROM cli_session_history").fetchall()
    cur = c.execute("SELECT channel, cli_session_id FROM sessions WHERE id=?", (sid,)).fetchone()
check("gắn phiên CLI mới: ghi lịch sử, dòng phiên giữ kênh agent",
      hist == [("cli-moi-2", sid)] and cur == ("agent:nguoi-lam-tom-tat", "cli-moi-2"), f"{hist} {cur}")

print(f"\n{'OK' if not fails else 'FAIL'}: {len(fails)} kiểm hỏng")
raise SystemExit(1 if fails else 0)
