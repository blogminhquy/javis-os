"""Hợp đồng tích hợp Zalo Agent MCP tối giản."""
import json

from _paths import ROOT, SERVER  # noqa: E402,F401
import mcp_catalog  # noqa: E402


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

check("catalog chỉ chạy MCP upstream đã ghim phiên bản",
      zalo["command"] == "npx"
      and zalo["args"] == ["-y", "zalo-agent-cli@1.6.2", "mcp", "start"])

expected_read = {
    "zalo_get_messages", "zalo_get_history", "zalo_list_threads",
    "zalo_search_threads", "zalo_view_media",
}
check("catalog khai đủ năm tool đọc", set(zalo["tool_meta"]["read"]) == expected_read)
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
check("doc nêu đủ bảy tool và link upstream",
      all(name in doc for name in expected_read | {"zalo_mark_read", "zalo_send_message"})
      and "https://github.com/PhucMPham/zalo-agent-cli" in doc)
check("prompt cho gửi trực tiếp, không phụ thuộc listener/tool cũ",
      "do NOT demand a listener be" in prompt
      and 'do NOT check any "currently listening"' in prompt
      and "do NOT use the old `javis_zalo_send` tool" in prompt)

if fails:
    raise SystemExit(f"{len(fails)} kiểm tra lỗi: {', '.join(fails)}")

print("OK: Zalo Agent MCP tối giản")
