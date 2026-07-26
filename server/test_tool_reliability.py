"""Hồi quy: mọi provider phải dùng tool thật cho cron/dữ liệu đang chạy.

Chạy:
    cd server && python test_tool_reliability.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tool-reliability-")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
from claude_cli import CodexCLI  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


schedule_tool = [{"fn": "javis_schedule", "description": "lịch", "schema": {
    "type": "object", "properties": {"op": {"type": "string"}},
}}]

check("intent cron tiếng Việt -> ép đúng javis_schedule",
      engine._tool_requirement(
          [{"role": "user", "content": "Kiểm tra toàn bộ cron/nhắc hẹn đang chạy và lịch thuốc hôm nay"}],
          schedule_tool) == "javis_schedule")
check("chat kiến thức thuần -> không ép tool",
      engine._tool_requirement(
          [{"role": "user", "content": "Cron expression là gì?"}], schedule_tool) is None)
check("dữ liệu Google hiện tại -> ép ít nhất một tool",
      engine._tool_requirement(
          [{"role": "user", "content": "Xem Google Tasks hiện có giúp anh"}],
          [{"fn": "javis_search_tools"}]) == "required")
check("câu chỉ xem lịch -> nhận ra đường read-only",
      engine._schedule_read_request(
          [{"role": "user", "content": "Kiểm tra cron đang chạy và lịch thuốc hôm nay"}]))
check("câu tạo lịch -> không dispatch nhầm thành read-only",
      not engine._schedule_read_request(
          [{"role": "user", "content": "Tạo lịch nhắc thuốc lúc 8h"}]))
check("câu XÓA cron -> ép đúng javis_schedule",
      engine._tool_requirement(
          [{"role": "user", "content": "Xóa cron brainstorm cách làm việc giúp anh"}],
          schedule_tool) == "javis_schedule")
check("câu XÓA cron -> nhận đúng mutation cancel",
      engine._schedule_cancel_request(
          [{"role": "user", "content": "Xóa cron brainstorm cách làm việc giúp anh"}]))
check("câu follow-up 'xoá cái vừa báo' -> vẫn nhận là cancel lịch",
      engine._schedule_cancel_request(
          [{"role": "user", "content": "Xóa cái vừa báo đi em"}]))


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = json.dumps(data)

    def json(self):
        return self._data


class FakeClient:
    payloads = []
    responses = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        self.__class__.payloads.append(json)
        return self.__class__.responses.pop(0)


async def tool_loop_tests():
    old_client = engine.httpx.AsyncClient
    old_call = mcp_client.call_route
    engine.httpx.AsyncClient = FakeClient

    async def fake_call(route, name, args):
        return "Lịch thật từ tool"

    mcp_client.call_route = fake_call
    try:
        FakeClient.payloads = []
        FakeClient.responses = [
            FakeResponse({"choices": [{"message": {"content": "Đã đọc lịch thật."}}]}),
        ]
        events = [e async for e in engine._cc_tool_loop(
            "https://fake", {}, "free-model",
            [{"role": "user", "content": "Kiểm tra cron đang chạy và lịch thuốc hôm nay"}],
            schedule_tool, {"javis_schedule": {}}, {}, "OpenRouter")]
        check("op=list được server dispatch trước khi gọi model",
              any(e.get("type") == "tool_call" and e.get("name") == "javis_schedule" for e in events))
        check("sau preflight list không còn ép model function-calling",
              "tool_choice" not in FakeClient.payloads[0])
        check("sau tool model được trả kết quả", any(e.get("content") == "Đã đọc lịch thật." for e in events))

        FakeClient.payloads = []
        FakeClient.responses = [
            FakeResponse({"choices": [{"message": {"content": "Tôi đoán là đã tạo."}}]}),
            FakeResponse({"choices": [{"message": {"content": "Vẫn không gọi tool."}}]}),
        ]
        ignored = [e async for e in engine._cc_tool_loop(
            "https://fake", {}, "free-model",
            [{"role": "user", "content": "Tạo cron nhắc thuốc lúc 8h"}],
            schedule_tool, {"javis_schedule": {}}, {}, "OpenRouter")]
        first_choice = FakeClient.payloads[0].get("tool_choice", {})
        check("thao tác tạo vẫn ép named tool_choice=javis_schedule",
              first_choice.get("function", {}).get("name") == "javis_schedule")
        check("model bỏ tool hai lần -> chặn câu trả lời bịa",
              any(e.get("type") == "error" and "bỏ qua tool bắt buộc" in e.get("content", "")
                  for e in ignored))
        check("không phát nội dung đoán khi model bỏ tool",
              not any(e.get("type") == "text" for e in ignored))
    finally:
        engine.httpx.AsyncClient = old_client
        mcp_client.call_route = old_call


asyncio.run(tool_loop_tests())


async def schedule_cancel_gateway_tests():
    old_call = mcp_client.call_route
    calls = []

    async def fake_call(route, name, args):
        calls.append((name, dict(args)))
        if args.get("op") == "list":
            return (
                "Nhắc hẹn / lịch (kho reminders):\n"
                "- [rem_a] Uống thuốc buổi sáng - 08:00 (lặp cron 0 8 * * *)\n"
                "- [rem_b] Brainstorm cách làm việc quan trọng hôm nay - 09:00 (lặp cron 0 9 * * *)"
            )
        if args.get("op") == "cancel":
            return f"Đã huỷ nhắc hẹn {args.get('id')}."
        return "ERROR: op"

    mcp_client.call_route = fake_call
    try:
        action = await engine.schedule_cancel_gateway(
            [{"role": "user", "content": "Xóa cron brainstorm cách làm việc quan trọng hôm nay"}],
            schedule_tool, {"javis_schedule": {}},
        )
        check("gateway chọn đúng cron theo tên duy nhất",
              action.get("handled") and action.get("id") == "rem_b")
        check("gateway tự gọi list rồi cancel, không phụ thuộc function-calling",
              calls == [
                  ("javis_schedule", {"op": "list"}),
                  ("javis_schedule", {"op": "cancel", "id": "rem_b"}),
              ])

        calls.clear()
        ambiguous = await engine.schedule_cancel_gateway(
            [{"role": "user", "content": "Xóa cron giúp anh"}],
            schedule_tool, {"javis_schedule": {}},
        )
        check("nhiều cron mà user không chỉ rõ -> không xoá nhầm",
              ambiguous.get("needs_choice") and
              not any(args.get("op") == "cancel" for _name, args in calls))

        async def fake_empty(route, name, args):
            return "Chưa có việc định kỳ hay nhắc hẹn nào."

        mcp_client.call_route = fake_empty
        empty = await engine.schedule_cancel_gateway(
            [{"role": "user", "content": "Xóa cron giúp anh"}],
            schedule_tool, {"javis_schedule": {}},
        )
        check("kho lịch trống -> báo không có, không nói mơ hồ/thiếu tool",
              empty.get("not_found") and not empty.get("needs_choice"))
    finally:
        mcp_client.call_route = old_call


asyncio.run(schedule_cancel_gateway_tests())


async def hub_vault_test():
    vault = tempfile.mkdtemp(prefix="javis-brain-")
    seen = []
    old_discover = mcp_hub.discover_all

    async def fake_discover(mode="full", vault_root=None, **kwargs):
        seen.append(vault_root)
        return [], {}

    class FakeRequest:
        headers = {
            "authorization": f"Bearer {mcp_hub.hub_token()}",
            "x-javis-mode": "full",
            "x-javis-vault": vault,
        }

        async def json(self):
            return {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    mcp_hub.discover_all = fake_discover
    try:
        response = await mcp_hub.handle_http(FakeRequest())
        check("hub HTTP tools/list thành công", response.status_code == 200)
        check("hub truyền X-Javis-Vault xuống plugin discovery",
              seen and Path(seen[0]).resolve() == Path(vault).resolve())
    finally:
        mcp_hub.discover_all = old_discover


asyncio.run(hub_vault_test())

vault = tempfile.mkdtemp(prefix="javis-codex-brain-")
override = mcp_hub.codex_vault_override(vault)
cli = CodexCLI(cwd=vault)
cli.cli_path = "codex"
cli.profile = "javis"
cli.extra_config.append(override)
args = cli._build_args()
check("Codex argv mang override X-Javis-Vault theo từng phiên",
      "-c" in args and override in args and "X-Javis-Vault" in override)

main_src = (Path(__file__).parent / "main.py").read_text(encoding="utf-8")
tg_src = main_src.split("async def _tg_answer", 1)[1].split("async def _tg_help_text", 1)[0]
check("Telegram ChatGPT đi qua CodexCLI thay vì chat-thuần",
      'if prov == "openai-oauth":' in tg_src and "CodexCLI(" in tg_src)
check("Telegram ChatGPT được gắn MCP hub đúng brain",
      "_apply_codex_hub(ccli, _brain_root(brain))" in tg_src)
check("lệnh /or không còn báo sai là không có MCP",
      "chat thuần, không MCP" not in main_src and "chat + MCP đa-model" in main_src)

if fails:
    print(f"\nFAIL - test_tool_reliability: {len(fails)} lỗi: {fails}")
    sys.exit(1)
print("\nOK - test_tool_reliability: tất cả pass")
