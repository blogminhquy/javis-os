"""Hợp đồng tích hợp Zalo Agent MCP tối giản."""
import io
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-zalo-mcp-"))

from _paths import ROOT, SERVER  # noqa: E402,F401
import mcp_catalog  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_login  # noqa: E402


fails = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}")
        fails.append(name)


catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
zalo = next(c for c in catalog["connectors"] if c["id"] == "zalo")
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
console_src = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
doc = (ROOT / "docs" / "12-zalo.md").read_text(encoding="utf-8")
prompt = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

check("catalog chạy bản CLI riêng javis-zalo ghim theo tag phát hành, dùng cache trước",
      zalo["command"] == "npx"
      and zalo["args"] == ["-y", "--prefer-offline", zalo_cli.CLI_PACKAGE, "mcp", "start"]
      and zalo_cli.CLI_PACKAGE.startswith("https://codeload.github.com/blogminhquy/javis-zalo/tar.gz/refs/tags/v"))
check("kết nối Zalo đã đăng nhập bằng bản 1.6.2 tự sang bản mới (lenh_cu)",
      {"command": "npx", "args": ["-y", "zalo-agent-cli@1.6.2", "mcp", "start"]} in zalo["lenh_cu"])

expected_read = {
    "zalo_get_messages", "zalo_get_history", "zalo_list_threads",
    "zalo_search_threads", "zalo_view_media", "zalo_search_history", "zalo_get_group_joins",
}
check("catalog khai đủ bảy tool đọc", set(zalo["tool_meta"]["read"]) == expected_read)
check("mark-read là ghi và send-message là nguy hiểm",
      mcp_catalog.classify(zalo, "zalo_mark_read") == "write"
      and mcp_catalog.classify(zalo, "zalo_send_message") == "danger")

check("backend không còn listener/webhook Zalo cũ",
      "zalo_listener_feature" not in main_src
      and "/hook/zalo" not in main_src
      and not (SERVER / "zalo_listener.py").exists()
      and not (SERVER / "zalo_rules.py").exists())
check("startup bật trả connector rồi xoá cấu hình listener cũ",
      '_legacy_cfg.pop("zalo_listener", None)' in main_src
      and 'mcp_store.update_connection(_legacy_conn, {"enabled": True})' in main_src)

check("frontend không còn gắn panel listener vào thẻ Zalo",
      'con.id === "zalo" ? zaloListenerPanel' not in console_src
      and "\n    wireZaloListener(el);" not in console_src)

check("hai plugin Zalo cũ đã được gỡ",
      not (ROOT / "system/plugins/zalo-rule/plugin.py").exists()
      and not (ROOT / "system/plugins/zalo-rule/plugin.yaml").exists()
      and not (ROOT / "system/plugins/zalo-send/plugin.py").exists()
      and not (ROOT / "system/plugins/zalo-send/plugin.yaml").exists())

guide_url = "https://github.com/blogminhquy/javis-os/blob/main/docs/12-zalo.md"
check("catalog trỏ nút hướng dẫn đến doc GitHub", zalo["auth"]["guide_url"] == guide_url)
check("doc nêu đủ chín tool và link repo javis-zalo",
      all(name in doc for name in expected_read | {"zalo_mark_read", "zalo_send_message"})
      and "https://github.com/blogminhquy/javis-zalo" in doc)
check("prompt cho gửi trực tiếp, không phụ thuộc listener/tool cũ",
      "do NOT demand a listener be" in prompt
      and 'do NOT check any "currently listening"' in prompt
      and "do NOT use the old `javis_zalo_send` tool" in prompt)


# Đăng nhập QR: CLI báo hỏng bằng {"event": "login_error", "message": ...} (src/commands/login.js). Trước 0.83.0 Javis
# chỉ nhận "error"/"failed", nên QR hết hạn hay bị Zalo từ chối thì modal không nói lý do thật.
class _FakeProc:
    def __init__(self, lines):
        self.stdout = io.StringIO("".join(x + "\n" for x in lines))
        self.stderr = io.StringIO("")

    def wait(self, timeout=None):
        return 0


def _login_session(lines):
    sid = "test-" + str(len(zalo_login._sessions))
    zalo_login._sessions[sid] = {"state": "starting", "qr": "", "label": "t", "conn_id": "", "error": "",
                                 "proc": _FakeProc(lines), "home": tempfile.mkdtemp(), "ts": 0}
    zalo_login._reader(sid)
    return zalo_login._sessions.pop(sid)


s = _login_session([
    '{"event":"qr_server","port":18927,"publicUrl":null}',
    '{"event":"qr","dataUrl":"data:image/png;base64,AAAA"}',
    '{"event":"login_error","message":"QR code expired"}',
])
check("đăng nhập QR: sự kiện login_error báo đúng câu lỗi của CLI",
      s["state"] == "error" and s["error"] == "QR code expired")

if fails:
    raise SystemExit(f"{len(fails)} kiểm tra lỗi: {', '.join(fails)}")

print("OK: Zalo Agent MCP tối giản")
