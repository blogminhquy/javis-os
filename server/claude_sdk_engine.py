"""
Engine Claude qua claude-agent-sdk CHÍNH CHỦ (Phase 1-2 của docs/dev/2026-07-ke-hoach-agent-sdk.md).

Đây là engine Claude DUY NHẤT từ v0.9.37 (nhánh ClaudeCLI Popen đã gỡ). Hợp đồng engine:
  - __init__(system_prompt, cwd, tag, allowed_tools, model) + các attr gán sau
    (session_id, mcp_config, mcp_strict, disallowed_tools, max_wall_s)
  - .query(prompt) -> async yield dict {type: text|tool_call|tool_result|final|error}
  - cancel_all(tag) interrupt theo họ tag (claude_cli.cancel_all gọi hộ)

Bật bằng env JAVIS_CLAUDE_ENGINE=sdk (mặc định cli - qua factory claude_cli.claude_engine).

Auth: engine KHÔNG bao giờ đọc token của ai. Nó chạy binary `claude` và để chính sản phẩm
của Anthropic lo đăng nhập - mặc định là phiên Claude Code sẵn có (gói subscription). Người
dùng chọn `api_key` ở trang Models thì `claude_auth.env_cho_cli` đưa ANTHROPIC_API_KEY xuống
tiến trình con. Hai lối cùng năng lực; khác nhau ở chỗ ai trả tiền. Xem claude_auth.py.

Nâng cấp so với CLI Popen: khi có allowed_tools (fork nền an toàn của loop/workflow),
quyền enforce PER-CALL bằng callback can_use_tool - tool ngoài whitelist bị TỪ CHỐI THẬT
từng lần gọi (kể cả Bash/Write builtin) + ghi audit, thay vì chỉ dựa --allowedTools tĩnh.
"""
import asyncio
import fnmatch
import json
import os
import sys
import threading
import time

try:
    import claude_agent_sdk as _sdk   # noqa: F401
    _SDK_OK = True
    # Tắt cảnh báo "can_use_tool bị allowed_tools che": đó CHÍNH là thiết kế của gate -
    # tool trong whitelist tự duyệt, mọi tool khác rơi vào _permission_gate → deny.
    import warnings as _warnings
    _warnings.filterwarnings("ignore", category=_sdk.CanUseToolShadowedWarning)
except Exception:
    _SDK_OK = False

from config import STATE_DIR

_AUDIT_PATH = STATE_DIR / "logs" / "sdk_tool_audit.jsonl"

# client đang chạy -> (tag, loop) để cancel_all interrupt theo họ tag như claude_cli
_ACTIVE = {}
_LOCK = threading.Lock()


def sdk_available() -> bool:
    return _SDK_OK


def cancel_all(tag=None) -> int:
    """Interrupt các phiên SDK đang chạy. tag=None → tất cả; khớp HỌ tag như claude_cli
    ('chat' ngắt cả 'chat:abc'). Trả số phiên đã ngắt."""
    with _LOCK:
        items = [(c, t, lp) for c, (t, lp) in _ACTIVE.items()
                 if tag is None or t == tag or str(t).startswith(str(tag) + ":")]
    for client, _t, loop in items:
        try:
            asyncio.run_coroutine_threadsafe(client.interrupt(), loop)
        except Exception:
            pass
    return len(items)


def _audit(tag, tool_name, allowed, reason=""):
    """Ghi 1 dòng audit quyết định quyền tool (JSONL). Lỗi ghi không được phá lượt chạy."""
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "tag": tag, "tool": tool_name,
                                "allowed": allowed, "reason": reason}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"[sdk-audit] {tag} {'ALLOW' if allowed else 'DENY '} {tool_name}"
          + (f" ({reason})" if reason else ""), file=sys.stderr)


def tran_watchdog(bien: str, mac_dinh: str):
    """Đọc một trần watchdog từ biến môi trường. Trả None = KHÔNG GIỚI HẠN.

    Vì sao có "không giới hạn", và vì sao nó là MẶC ĐỊNH của trần im-giữa-chừng: watchdog đo
    "bao lâu rồi chưa nhận được message từ SDK" rồi coi đó là treo. Phép đo ấy sai ở một ca
    rất thường gặp - SDK chỉ phát message khi model KẾT THÚC một khối, nên suốt lúc model suy
    nghĩ ở mức nỗ lực cao, hoặc lúc nó soạn nội dung một file dài để đưa vào tool Write, kênh
    im hoàn toàn dù mọi thứ đang chạy đúng. Chủ repo dính đúng ca đó (2026-08-07): bảo Javis
    "thiết kế cho anh file .md", Javis nói "viết file luôn" rồi bị chém ở giây thứ 180 giữa
    lúc đang soạn file.

    Cắt một lượt đang chạy tốt tệ hơn hẳn để nó chạy lâu: người dùng luôn bấm Dừng được, và
    việc nền thì đã có trần wall-clock riêng (`max_wall_s`) nên không treo vô hạn.

    0 hoặc số âm = không giới hạn. Chuỗi rác cũng về mặc định chứ không làm nổ lượt chat.
    """
    raw = os.getenv(bien, mac_dinh)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = float(mac_dinh)
    return v if v > 0 else None


_INIT_MAC_DINH = "300"    # giây - trần chờ `claude` khởi động xong (SDK mặc định chỉ 60)


def ap_tran_khoi_dong():
    """Nới trần chờ control request `initialize` của SDK. Trả số giây đang áp dụng (None = giữ
    nguyên biến người dùng tự đặt).

    Vì sao cần: lúc initialize, `claude` phải đấu XONG mọi MCP server rồi mới nhận việc, mà SDK
    chờ đúng 60 giây rồi ném `Control request timeout: initialize`. Máy đấu nhiều nguồn (hub
    Javis + connector tài khoản Claude) vượt 60s là chuyện thường, và người dùng nhận về một
    dòng tiếng Anh trần trụi sau khi ngồi chờ - đúng ca báo ngày 2026-08-11.

    SDK chỉ đọc trần này qua env `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT` (mili giây, sàn cứng 60s)
    chứ KHÔNG có tham số nào trong options, nên phải đặt env của chính tiến trình server. Ai đã
    tự đặt biến của SDK thì tôn trọng, không đè.
    """
    raw = os.getenv("JAVIS_CLAUDE_INIT_TIMEOUT")
    if raw is None and os.getenv("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"):
        return None
    try:
        giay = float(raw if raw is not None else _INIT_MAC_DINH)
    except (TypeError, ValueError):
        giay = float(_INIT_MAC_DINH)
    giay = max(giay, 60.0)   # SDK có sàn 60s; đặt thấp hơn chỉ là tự lừa mình
    os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"] = str(int(giay * 1000))
    return giay


def loi_de_hieu(e, tran_init=None):
    """Đổi exception của SDK thành câu người dùng ĐỌC RA ĐƯỢC VIỆC PHẢI LÀM.

    Mẫu nào không khớp thì giữ nguyên chuỗi gốc: đoán bừa nguyên nhân còn tệ hơn tiếng Anh trần.
    """
    raw = str(e)
    if "Control request timeout: initialize" in raw:
        n = f"{int(tran_init)}s" if tran_init else "trần cho phép"
        return ("Claude Code không khởi động xong trong " + n + " nên lượt này bị huỷ. Gần như "
                "luôn là do NGUỒN DỮ LIỆU (MCP): lúc khởi động, Claude phải kết nối xong mọi "
                "nguồn rồi mới nhận việc, nên một nguồn chết hoặc chậm là kéo cả lượt chờ theo "
                "rồi hết giờ. Mở trang Kết nối, bấm Kiểm tra để tìm nguồn đang đỏ rồi tắt nó đi "
                "và gửi lại tin nhắn. (JAVIS_CLAUDE_INIT_TIMEOUT=<giây> để nới thêm trần này)")
    if "Control request timeout:" in raw:
        return (f"Claude Code không phản hồi lệnh điều khiển ({raw}). Gửi lại tin nhắn; còn lặp "
                "lại thì mở hội thoại mới.")
    return f"SDK engine: {type(e).__name__}: {e}"


def map_message(msg):
    """Map 1 message SDK → (list event dict 'hợp đồng ClaudeCLI', session_id|None).
    PURE - test offline được, không cần CLI/auth."""
    from claude_agent_sdk import (AssistantMessage, UserMessage, SystemMessage, ResultMessage,
                                  TextBlock, ToolUseBlock, ToolResultBlock)
    events = []
    if isinstance(msg, SystemMessage):
        return events, (msg.data or {}).get("session_id")
    if isinstance(msg, AssistantMessage):
        for b in msg.content:
            if isinstance(b, TextBlock):
                if (b.text or "").strip():
                    events.append({"type": "text", "content": b.text})
            elif isinstance(b, ToolUseBlock):
                events.append({"type": "tool_call", "name": b.name or "", "input": b.input or {}})
        return events, None
    if isinstance(msg, UserMessage):
        content = msg.content
        if isinstance(content, list):
            for b in content:
                if isinstance(b, ToolResultBlock):
                    c = b.content
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    events.append({"type": "tool_result", "content": str(c or "")[:500]})
        return events, None
    if isinstance(msg, ResultMessage):
        u = msg.usage or {}
        # Đèn báo não: kết quả cuối khớp mẫu lỗi đăng nhập → bật đèn đỏ trên dashboard
        # + Telegram; chạy sạch thì tắt đèn. Não chết không tự báo được nên phải bắt ở đây.
        try:
            import connect_health
            if not connect_health.flag_engine_auth_error("claude", msg.result or ""):
                if not msg.is_error:
                    connect_health.engine_run_ok("claude")
        except Exception:
            pass
        # Kết thúc LỖI mà không có chữ nào trả về → nói rõ lý do thay vì để dashboard
        # hiện "(không có nội dung trả về)" trơ trọi (hay gặp sau khi phiên trước bị ngắt).
        if msg.is_error and not (msg.result or "").strip():
            events.append({"type": "error",
                           "content": f"Claude kết thúc lỗi ({msg.subtype}) - không có nội dung trả về. "
                                      "Gửi lại tin nhắn; nếu vẫn lặp lại, mở hội thoại mới "
                                      "(phiên cũ có thể đã hỏng sau khi bị ngắt giữa chừng)."})
        events.append({
            "type": "final",
            "content": msg.result or "",
            "session_id": msg.session_id,
            "cost_usd": msg.total_cost_usd,
            "duration_ms": msg.duration_ms,
            "tokens_in": ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                          + (u.get("cache_creation_input_tokens") or 0)),
            "tokens_out": u.get("output_tokens") or 0,
        })
        return events, msg.session_id
    return events, None


class ClaudeSDK:
    """Engine Claude qua Agent SDK - engine Claude duy nhất (tạo qua claude_cli.claude_engine)."""

    def __init__(self, system_prompt=None, cwd=None, tag="chat", allowed_tools=None, model=None):
        self.system_prompt = system_prompt
        self.cwd = cwd or os.getcwd()
        self.session_id = None
        self.tag = tag
        self.allowed_tools = allowed_tools
        self.model = model
        self.mcp_config = None
        self.mcp_strict = False
        self.disallowed_tools = None
        self.max_wall_s = None
        self.javis_mode = None    # _apply_mcp đặt (suggest|auto|full) - enforce min_mode plugin in-process
        self.javis_vault = None   # _apply_mcp đặt - brain đang làm việc, cho ctx của plugin
        # True = gửi system_prompt TRẦN, bỏ preset claude_code. Đường tiết kiệm token dùng cái
        # này: cả giá trị của nó nằm ở chỗ system prompt chỉ còn vài trăm token, mà preset
        # claude_code thì tự nhét lại prompt đầy đủ của Claude Code và ăn sạch phần tiết kiệm.
        self.system_prompt_raw = False
        self._tmp_files = []      # file tạm (system prompt) dọn sau mỗi query

    def is_available(self) -> bool:
        if not _SDK_OK:
            return False
        from claude_cli import find_claude_cli
        return find_claude_cli() is not None

    def reset_session(self):
        self.session_id = None

    async def _permission_gate(self, tool_name, input_data, context):
        """can_use_tool: whitelist THẬT per-call khi chạy chế độ nền an toàn (allowed_tools).
        Hỗ trợ pattern fnmatch (vd 'mcp__javis__pos_*') VÀ prefix kiểu --allowedTools của
        Claude CLI: 'mcp__<server>' trần (không wildcard) = cho MỌI tool của server đó.
        Thiếu nhánh prefix thì pattern 'mcp__javis' từ mcp_hub.allow_patterns() không khớp
        tool nào → lane nền (kanban/loop) bị chặn sạch MCP dù connector sống."""
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        allowed = self.allowed_tools or []
        ok = any(tool_name == p or fnmatch.fnmatch(tool_name, p)
                 or (p.startswith("mcp__") and "*" not in p
                     and tool_name.startswith(p + "__"))
                 for p in allowed)
        _audit(self.tag, tool_name, ok, "" if ok else "ngoài whitelist chế độ nền an toàn")
        if ok:
            return PermissionResultAllow()
        # Nói RÕ đây là rào quyền của phiên nền, KHÔNG phải connector/MCP hỏng - thiếu câu này
        # agent từng suy diễn "OAuth chết / cần re-auth" rồi kết luận sai cho user (vụ 0.9.189).
        extra = ""
        if tool_name.startswith("mcp__"):
            extra = (" Kết nối MCP/connector KHÔNG hỏng - đừng thử đăng nhập lại hay chẩn đoán "
                     "OAuth. Việc này cần quyền rộng hơn thì báo lại người giao việc.")
        return PermissionResultDeny(
            message=f"Tool '{tool_name}' bị chặn bởi rào quyền phiên nền an toàn: phiên này chỉ "
                    f"được dùng {', '.join(allowed)}.{extra}")

    def _plugins_server(self):
        """Phase 3: dựng MCP server IN-PROCESS từ tool plugin (plugins_host) - engine SDK gọi
        thẳng handler Python, không qua hub HTTP. Trả McpSdkServerConfig hoặc None (không plugin).
        min_mode enforce sẵn trong route của plugin_tools(mode); hook pre/post bọc như hub."""
        import plugins_host
        from claude_agent_sdk import tool as sdk_tool, create_sdk_mcp_server
        mode = (self.javis_mode or "full").strip().lower()
        # vault_root: CHỈ để ctx của plugin biết đang làm việc ở brain nào (vd image-chatgpt lưu
        # ảnh vào đúng attachments/). self.javis_vault do _apply_mcp đặt TƯỜNG MINH (main.py) -
        # KHÔNG suy từ cwd: chat chạy với cwd = gốc project (CLAUDE_CWD), không phải thư mục
        # brain, nên suy từ cwd luôn trượt đúng ở đường chat - nơi bug thật sự xảy ra.
        # Vẫn KHÔNG nạp plugin riêng-của-vault (giữ nguyên hành vi cũ): scope_vault=False.
        p_tools, p_route = plugins_host.plugin_tools(mode, self.javis_vault, scope_vault=False)
        if not p_tools:
            return None
        # has_tool_hooks/wrap_with_hooks chưa biết scope_vault (ngoài phạm vi task này) - giữ
        # nguyên vault_root=None ở đây để KHÔNG vô tình nạp plugin riêng-của-vault qua nhánh
        # _load_all(vault_root) mặc định scope_vault=True của chúng.
        use_hooks = plugins_host.has_tool_hooks(None)
        sdk_tools = []
        for t in p_tools:
            fn = t["fn"]
            call = p_route[fn]["call"]
            if use_hooks:
                call = plugins_host.wrap_with_hooks(fn, call, mode, None)

            async def _handler(args, _call=call):
                res = await _call(args or {})
                return {"content": [{"type": "text", "text": str(res)}]}

            sdk_tools.append(sdk_tool(fn, t.get("description") or fn,
                                      t.get("schema") or {"type": "object", "properties": {}})(_handler))
        return create_sdk_mcp_server("javis-plugins", tools=sdk_tools)

    def _mcp_servers(self):
        """(mcp_servers cho options, strict) - đọc file config (đường _apply_mcp) thành dict,
        đấu thêm plugin in-process khi KHÔNG gated. Gated fork (allowed_tools) giữ nguyên
        cô lập như CLI: chỉ file config (thường là MCP rỗng), KHÔNG plugin in-process."""
        servers = None
        if self.mcp_config:
            try:
                with open(self.mcp_config, encoding="utf-8") as f:
                    servers = dict(json.load(f).get("mcpServers") or {})
            except Exception as e:
                print(f"[sdk engine] đọc mcp_config lỗi ({e}) - truyền path thô", file=sys.stderr)
                return str(self.mcp_config), self.mcp_strict
        if self.allowed_tools:
            return servers, self.mcp_strict
        try:
            plug = self._plugins_server()
        except Exception as e:
            print(f"[sdk engine] plugin in-process lỗi: {type(e).__name__}: {e}", file=sys.stderr)
            plug = None
        if plug is not None:
            servers = dict(servers or {})
            servers["javis-plugins"] = plug
            hub = servers.get("javis")
            if isinstance(hub, dict) and hub.get("headers") is not None:
                # Báo hub bỏ nhóm plugin - model không thấy 2 tool trùng chức năng
                hub = dict(hub); hub["headers"] = dict(hub["headers"])
                hub["headers"]["X-Javis-No-Plugins"] = "1"
                servers["javis"] = hub
        return servers, self.mcp_strict

    def _write_sysprompt_file(self, text):
        """Ghi system prompt ra file tạm để truyền qua --append-system-prompt-file.
        Trả path; nhớ vào _tmp_files để query() dọn sau."""
        import tempfile
        try:
            d = STATE_DIR / "tmp"
            d.mkdir(parents=True, exist_ok=True)
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="javis-sysprompt-", dir=str(d))
        except Exception:
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="javis-sysprompt-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        self._tmp_files.append(path)
        return path

    def _cleanup_tmp(self):
        for p in self._tmp_files:
            try:
                os.unlink(p)
            except Exception:
                pass
        self._tmp_files = []

    @staticmethod
    def _sweep_stale_tmp(max_age_s=3600):
        """Dọn file system prompt tạm còn sót (crash/kill giữa lượt không kịp finally).
        Best-effort: bỏ qua mọi lỗi, chỉ xoá file cũ hơn max_age_s."""
        try:
            d = STATE_DIR / "tmp"
            if not d.exists():
                return
            now = time.time()
            for f in d.glob("javis-sysprompt-*.txt"):
                try:
                    if now - f.stat().st_mtime > max_age_s:
                        f.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _options(self):
        from claude_agent_sdk import ClaudeAgentOptions
        fields = getattr(ClaudeAgentOptions, "__dataclass_fields__", {})
        kw = {"cwd": self.cwd}
        # System prompt đẩy qua FILE (--append-system-prompt-file) thay vì nhét vào THAM SỐ dòng lệnh.
        # Trên Windows tổng dòng lệnh > 32767 ký tự thì CreateProcess CHẾT: Python báo FileNotFoundError,
        # SDK dán nhãn nhầm "Claude Code not found at ...\\_bundled\\claude.exe". System prompt của Javis
        # (CLAUDE.md + bộ nhớ brain nhiều note) dễ vượt ngưỡng -> đây là gốc lỗi đó. Đọc qua file thì
        # không còn giới hạn độ dài. SDK cũ không có extra_args thì fallback nhét inline (chỉ hợp prompt ngắn).
        if self.system_prompt and self.system_prompt_raw:
            # Trần: KHÔNG preset. Đây là đường tiết kiệm token - thêm preset vào là mất sạch
            # phần tiết kiệm. Vẫn đi qua binary `claude` nên vẫn là đường chính chủ.
            kw["system_prompt"] = self.system_prompt
        elif self.system_prompt and "extra_args" in fields:
            _p = self._write_sysprompt_file(self.system_prompt)
            kw["system_prompt"] = {"type": "preset", "preset": "claude_code"}
            kw["extra_args"] = {"append-system-prompt-file": _p}
        elif self.system_prompt:
            kw["system_prompt"] = {"type": "preset", "preset": "claude_code", "append": self.system_prompt}
        else:
            kw["system_prompt"] = {"type": "preset", "preset": "claude_code"}
        # SDK mặc định chặn 1 message stdio ở 1MB. Tool trả ảnh (đọc frame video,
        # ảnh chụp màn hình) vượt ngưỡng này là vỡ buffer -> SDKJSONDecodeError.
        if "max_buffer_size" in getattr(ClaudeAgentOptions, "__dataclass_fields__", {}):
            kw["max_buffer_size"] = 32 * 1024 * 1024
        # Chế độ API key: đưa ANTHROPIC_API_KEY xuống tiến trình `claude`. Phải MERGE với
        # os.environ chứ không thay thế - SDK truyền thẳng dict này cho tiến trình con, và một
        # env chỉ có mỗi API key là mất PATH, mất HOME, tiến trình chết trước khi kịp chào.
        try:
            import claude_auth
            _env = claude_auth.env_cho_cli()
        except Exception as e:   # noqa: BLE001 - đọc cấu hình hỏng không được phá lượt chat
            print(f"[sdk engine] không đọc được chế độ auth: {type(e).__name__}: {e}", file=sys.stderr)
            _env = {}
        if _env and "env" in fields:
            kw["env"] = {**os.environ, **_env}
        if self.model:
            kw["model"] = self.model
        if self.session_id:
            kw["resume"] = self.session_id
        servers, strict = self._mcp_servers()
        if servers is not None:
            kw["mcp_servers"] = servers
            if strict:
                kw["strict_mcp_config"] = True
        if self.disallowed_tools:
            kw["disallowed_tools"] = list(self.disallowed_tools)
        if self.allowed_tools:
            # Chế độ nền an toàn: whitelist auto-allow, MỌI tool khác rơi vào _permission_gate → DENY.
            # KHÔNG nạp settings filesystem: allow-rule trong settings user có thể che gate.
            kw["allowed_tools"] = list(self.allowed_tools)
            kw["permission_mode"] = "default"
            kw["can_use_tool"] = self._permission_gate
        else:
            kw["permission_mode"] = "bypassPermissions"   # parity --dangerously-skip-permissions
            # Parity CLI: nạp settings máy (ambient MCP, CLAUDE.md, config user) như claude -p vẫn làm
            kw["setting_sources"] = ["user", "project", "local"]
        return ClaudeAgentOptions(**kw)

    async def query(self, prompt: str):
        if not self.is_available():
            yield {"type": "error", "content": "claude-agent-sdk chưa sẵn sàng (pip install claude-agent-sdk "
                                               "+ cài/đăng nhập Claude Code CLI)."}
            return
        from claude_agent_sdk import ClaudeSDKClient, ResultMessage
        # Ba trần watchdog, None = không giới hạn. Xem `tran_watchdog` để biết vì sao hai trần
        # đo-sự-im-lặng-của-model mặc định là KHÔNG GIỚI HẠN: im lặng không đồng nghĩa với treo,
        # và chém oan một lượt đang chạy tốt là mất trắng cả công lẫn token.
        IDLE = tran_watchdog("JAVIS_CLAUDE_IDLE_TIMEOUT", "0")
        # Trần RIÊNG khi đang chờ TOOL chạy. Cái này đo một thứ CÓ THẬT: tool đã khởi động mà
        # chưa trả kết quả, tức có một tiến trình con đang sống ngoài kia. Giữ trần 1 tiếng để
        # một lệnh treo (chờ nhập liệu, khoá file...) không giữ phiên mãi mãi.
        TOOL_IDLE = tran_watchdog("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600")
        # Trần RIÊNG cho SỰ KIỆN ĐẦU TIÊN. Cùng họ với IDLE: hội thoại càng dài thì lượt đầu
        # càng lâu (nạp lại ngữ cảnh lớn, model suy nghĩ trước khi phát chữ, đôi khi SDK còn tự
        # nén lịch sử), nên cũng để không giới hạn.
        FIRST_IDLE = tran_watchdog("JAVIS_CLAUDE_FIRST_TIMEOUT", "0")
        self._sweep_stale_tmp()   # dọn file prompt tạm sót từ lượt trước bị crash/kill
        # Nới trần `initialize` TRƯỚC khi dựng client: SDK đọc env ngay trong connect().
        tran_init = ap_tran_khoi_dong()
        loop = asyncio.get_running_loop()
        client = ClaudeSDKClient(options=self._options())
        started = time.time()
        tools_running = 0   # số tool đã gọi mà CHƯA thấy kết quả về
        da_co_chu = False   # đã nhận được sự kiện đầu tiên chưa (quyết định dùng trần nào)
        try:
            await client.connect()
            with _LOCK:
                _ACTIVE[client] = (self.tag, loop)
            await client.query(prompt)
            agen = client.receive_response().__aiter__()
            while True:
                # Watchdog parity với CLI: idle-timeout + trần wall-clock cho fork nền.
                # Chốt trần VÀ lý do cùng lúc: trần nào cũng có thể bị đặt "không giới hạn",
                # nên suy ngược lý do lúc hết giờ là đường dẫn tới thông báo sai (và tới
                # int(None) nổ giữa lượt chat).
                waiting_tool = tools_running > 0
                if waiting_tool:
                    tran, ly_do = TOOL_IDLE, "tool"
                elif da_co_chu:
                    tran, ly_do = IDLE, "im"
                else:
                    tran, ly_do = FIRST_IDLE, "dau"
                if self.max_wall_s:
                    con_lai = max(1.0, self.max_wall_s - (time.time() - started))
                    if tran is None or con_lai < tran:
                        tran, ly_do = con_lai, "wall"
                try:
                    msg = await asyncio.wait_for(agen.__anext__(), timeout=tran)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    if ly_do == "wall":
                        err = f"Fork vượt trần {int(self.max_wall_s)}s - đã dừng (cap wall-clock nền)."
                    elif ly_do == "tool":
                        err = (f"Tool chạy quá {int(TOOL_IDLE)}s chưa xong - đã dừng để tránh treo server. "
                               f"(tăng JAVIS_CLAUDE_TOOL_TIMEOUT nếu tác vụ thật sự dài hơn, "
                               f"đặt 0 để bỏ hẳn trần)")
                    elif ly_do == "dau":
                        err = (f"Claude chưa trả lời gì sau {int(FIRST_IDLE)}s - đã dừng để tránh treo "
                               f"server. Hay gặp khi hội thoại đã rất dài: lượt đầu phải nạp lại toàn bộ "
                               f"ngữ cảnh nên lâu. Mở hội thoại mới thường hết ngay. "
                               f"(JAVIS_CLAUDE_FIRST_TIMEOUT=0 để bỏ hẳn trần này)")
                    else:
                        err = (f"Claude đang trả lời rồi im {int(IDLE)}s - đã dừng để tránh treo server. "
                               f"(JAVIS_CLAUDE_IDLE_TIMEOUT=0 để bỏ hẳn trần này)")
                    try:
                        await client.interrupt()
                    except Exception:
                        pass
                    yield {"type": "error", "content": err}
                    break
                da_co_chu = True   # có sự kiện đầu tiên → từ đây dùng trần ngắn IDLE
                events, sid = map_message(msg)
                if sid:
                    if sid != self.session_id and self.javis_vault:
                        # Nhãn dự án cho trang Token: log thô chỉ có cwd (= gốc project ở MỌI
                        # phiên), nên ghi riêng phiên này thuộc brain nào. Xem session_brain.py.
                        try:
                            import session_brain
                            session_brain.record(sid, self.javis_vault)
                        except Exception:
                            pass
                    self.session_id = sid
                for ev in events:
                    if ev["type"] == "tool_call":
                        tools_running += 1
                    elif ev["type"] == "tool_result":
                        tools_running = max(0, tools_running - 1)
                    yield ev
                if isinstance(msg, ResultMessage):
                    break
        except Exception as e:
            yield {"type": "error", "content": loi_de_hieu(e, tran_init)}
        finally:
            with _LOCK:
                _ACTIVE.pop(client, None)
            try:
                await client.disconnect()
            except Exception:
                pass
            self._cleanup_tmp()   # xoá file system prompt tạm của lượt này
