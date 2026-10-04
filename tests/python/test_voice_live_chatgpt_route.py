"""Route /ws/voice-live với ChatGPT Live (0.65.17). Không mạng, không Codex thật.

    python tests/run.py voice_live_chatgpt_route

Chạy riêng hàm route (khuôn của test_voice_live_focus.py) với nhà cung cấp giả. Khoá:
  - ChatGPT Live: bắc cầu token sang Codex và nạp mục lục bộ nhớ trước khi dựng nhà cung cấp;
  - khung ready mang transport "webrtc";
  - khung webrtc_offer từ trình duyệt được trả bằng webrtc_answer;
  - giao việc: bong bóng tool_result mang bản ĐẦY ĐỦ, lưu vào lịch sử, rồi mới trả model.
"""
from _paths import ROOT, SERVER  # noqa: F401
import ast
import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import sessions
import voice_live


class ChatGPTLiveRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_webrtc_handshake_and_full_tool_result(self):
        with tempfile.TemporaryDirectory() as directory:
            store = sessions.SessionStore(str(Path(directory) / "sessions.db"))
            sid = store.get_or_create(None, brain="brain", engine="test", model="test")
            mem_dir = Path(directory) / "memory"
            mem_dir.mkdir()
            (mem_dir / "MEMORY.md").write_text("- [Xưng hô](x.md) - chủ xưng anh", encoding="utf-8")
            frames, calls = [], {"auth": 0, "memory": None, "offer": None, "results": []}
            tool_done = asyncio.Event()

            class Provider:
                name = "chatgpt"
                model = ""
                transport = "webrtc"
                wants_reconnect = False

                async def connect(self): pass
                async def restore_history(self, history): pass
                def supports_async_tools(self): return True
                async def close(self): pass
                async def send_tool_running(self, cid, name): pass
                async def send_context(self, text): pass

                async def start_webrtc(self, sdp):
                    calls["offer"] = sdp
                    return "v=0 answer"

                async def send_tool_result(self, cid, name, result):
                    calls["results"].append(result)

                async def events(self):
                    yield {"type": "tool_call", "id": "h1", "name": "ask_javis",
                           "args": {"request": "Doanh thu hôm nay"}}
                    await asyncio.Event().wait()

            provider = Provider()

            def make_provider(cfg, recognition_lang="vi-VN", memory_index=""):
                calls["memory"] = memory_index
                return provider

            class Socket:
                def __init__(self):
                    self.n = 0

                async def accept(self): pass

                async def send_text(self, text):
                    frame = json.loads(text)
                    frames.append(frame)
                    if frame.get("type") == "tool" and frame.get("status") == "done":
                        tool_done.set()

                async def receive(self):
                    self.n += 1
                    if self.n == 1:
                        return {"text": json.dumps({"type": "webrtc_offer", "sdp": "v=0 offer"})}
                    await tool_done.wait()
                    await asyncio.sleep(0.05)
                    return {"text": '{"type":"stop"}'}

                async def close(self): pass

            async def ask(req, conv_sid, brain, key="", progress=None):
                return "## Doanh thu hôm nay\n\n| Kênh | Tiền |\n|---|---|\n| POS | 12.500.000 |"

            def write_auth():
                calls["auth"] += 1

            namespace = dict(
                asyncio=asyncio, json=json, sys=sys, WebSocket=Socket, Query=lambda x: x,
                cfgmod=types.SimpleNamespace(gate_active=lambda: False,
                                             read_settings=lambda: {"voice": {"live_provider": "chatgpt"}}),
                voice_live=types.SimpleNamespace(
                    make_provider=make_provider, MEMORY_CHARS=4000,
                    # the route's long-job heartbeat reads these as soon as a job starts
                    STATUS_FIRST_S=voice_live.STATUS_FIRST_S, STATUS_EVERY_S=voice_live.STATUS_EVERY_S,
                    STATUS_TICK_S=voice_live.STATUS_TICK_S),
                openai_oauth=types.SimpleNamespace(write_codex_auth=write_auth),
                _brain_memory_dir=lambda root: mem_dir, _brain_root=lambda b: directory,
                _fit_memory_index=lambda mem, cap=None: mem[:cap],
                _voice_ask_javis=ask, get_store=lambda: store, _brain_key=lambda b: b,
                voice_call=types.SimpleNamespace(live_settings=lambda c: c))
            tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
            route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "voice_live_ws")
            route.decorator_list = []
            exec(compile(ast.Module(body=[route], type_ignores=[]), "live-route", "exec"), namespace)
            try:
                await asyncio.wait_for(namespace["voice_live_ws"](Socket(), sid, "brain", "vi-VN"), 5)
                ready = next(f for f in frames if f["type"] == "ready")
                self.assertEqual(ready["transport"], "webrtc")
                self.assertEqual(calls["auth"], 1, "token ChatGPT phải được bắc cầu sang Codex")
                self.assertIn("chủ xưng anh", calls["memory"])
                self.assertEqual(calls["offer"], "v=0 offer")
                self.assertIn({"type": "webrtc_answer", "sdp": "v=0 answer"}, frames)
                types_in_order = [f["type"] + ":" + str(f.get("status", "")) for f in frames
                                  if f["type"] in ("tool", "tool_result")]
                self.assertEqual(types_in_order, ["tool:running", "tool_result:", "tool:done"])
                full = next(f for f in frames if f["type"] == "tool_result")
                self.assertIn("12.500.000", full["text"])
                self.assertIn("| POS |", full["text"], "bong bóng giữ bảng đầy đủ")
                self.assertEqual(len(calls["results"]), 1)
                saved = [m["content"] for m in store.get_messages(sid) if m["role"] == "assistant"]
                self.assertTrue(any("12.500.000" in m for m in saved), "kết quả đầy đủ vào lịch sử")
            finally:
                store._conn.close()


if __name__ == "__main__":
    unittest.main()
