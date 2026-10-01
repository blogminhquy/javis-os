"""ChatGPT Live không lặp câu trả lời (0.65.21). Không mạng, không Codex thật.

    python tests/run.py voice_live_followup

Lỗi chủ dự án báo 01/10/2026 (tái hiện được trên dashboard thật): đang chờ Javis làm việc, người dùng
nói thêm "Ok, xem xong kiểm tra xong thì báo anh nhé". Model nói chuyện coi câu đó là một lần giao
việc nữa (Codex coi handoff tới giữa chừng là lời CHỈNH HƯỚNG việc đang chạy), Javis chạy bộ não chính
lần hai, ra hai bong bóng kết quả khác chữ, rồi lời đọc lại tóm tắt thành bong bóng thứ ba. Khoá:
  - câu nói thêm chỉ là xác nhận/nhắc báo: không chạy bộ não lần nữa, không bong bóng;
  - câu nói thêm có yêu cầu thật: chạy SAU việc đang chạy, kèm yêu cầu trước làm ngữ cảnh;
    bộ não trả JAVIS_NOOP thì không bong bóng, không đọc;
  - lời model đọc lại kết quả (đã có bong bóng đầy đủ) không thành bong bóng thứ hai, không vào lịch sử;
  - lời Javis sau khi người dùng nói tiếp vẫn hiện như thường.
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


class FollowupWordsTests(unittest.TestCase):
    def test_ack_words(self):
        for text in ("Ok, xem xong kiểm tra xong thì báo anh nhé", "ok em", "Dạ được rồi, cảm ơn em nhé",
                     "Xong thì báo anh nha", "ok Javis, làm luôn đi", "okay let me know when done"):
            self.assertTrue(voice_live.is_followup_ack(text), text)
        for text in ("", "thêm cả số đơn huỷ nữa", "kiểm tra cả email nữa", "thôi không cần nữa",
                     "à mà doanh thu tháng trước bao nhiêu", "Ok, xem lịch tuần này luôn"):
            self.assertFalse(voice_live.is_followup_ack(text), text)

    def test_same_request(self):
        q = "Javis ơi, xem giúp anh trong Brain có những ghi chú nào, liệt kê 5 cái mới nhất"
        self.assertTrue(voice_live.is_same_request(q, q))
        self.assertTrue(voice_live.is_same_request(q, "liệt kê 5 cái mới nhất"))
        self.assertFalse(voice_live.is_same_request(q, q + " và cả lịch tuần này"), "thêm ý mới thì không phải lặp")
        self.assertFalse(voice_live.is_same_request("xem anh", "an"), "khớp theo từ, không theo mảnh chữ")
        self.assertFalse(voice_live.is_same_request("", "xem lịch"))

    def test_followup_request_and_noop(self):
        req = voice_live.followup_request("Doanh thu hôm nay", "thêm cả số đơn huỷ nữa")
        self.assertIn("Doanh thu hôm nay", req)
        self.assertIn("thêm cả số đơn huỷ nữa", req)
        self.assertIn(voice_live.FOLLOWUP_NOOP, req)
        self.assertTrue(voice_live.is_noop_result("JAVIS_NOOP"))
        self.assertTrue(voice_live.is_noop_result("`JAVIS_NOOP`\n"))
        self.assertFalse(voice_live.is_noop_result("Số đơn huỷ hôm nay là 3. " * 10 + "JAVIS_NOOP"))
        self.assertFalse(voice_live.is_noop_result("Số đơn huỷ hôm nay là 3."))

    def test_chatgpt_ack_is_silent_and_prompt_says_no_redelegation(self):
        self.assertIn("đang chờ", voice_live.CHATGPT_LIVE_PROMPT)
        live = voice_live.ChatGPTLive(app_server_getter=lambda: None)
        asyncio.run(live.send_tool_ack("h2", "ask_javis", "x"))   # không gọi app-server nào


def _route():
    tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
    route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "voice_live_ws")
    route.decorator_list = []
    return ast.Module(body=[route], type_ignores=[])


class LiveRouteFollowupTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, script, answers):
        """Chạy route với nhà cung cấp giả; `script(prov, h)` đẩy sự kiện, `answers` trả lời của bộ não."""
        with tempfile.TemporaryDirectory() as directory:
            store = sessions.SessionStore(str(Path(directory) / "sessions.db"))
            try:
                return await self._run_in(store, directory, script, answers)
            finally:
                store._conn.close()

    async def _run_in(self, store, directory, script, answers):
        if True:
            sid = store.get_or_create(None, brain="brain", engine="test", model="test")
            frames, asks = [], []
            inbox = asyncio.Queue()   # khung trình duyệt gửi lên

            class Provider:
                name = "chatgpt"
                model = ""
                transport = "webrtc"
                wants_reconnect = False

                def __init__(self):
                    self.q = asyncio.Queue()
                    self.results, self.acks = [], []

                async def connect(self): pass
                async def restore_history(self, history): pass
                def supports_async_tools(self): return True
                async def close(self): pass
                async def send_tool_running(self, cid, name): pass
                async def send_context(self, text): pass

                async def send_tool_result(self, cid, name, result):
                    self.results.append((cid, result))

                async def send_tool_ack(self, cid, name, text):
                    self.acks.append(cid)

                async def send_text(self, text):
                    pass

                async def events(self):
                    while True:
                        ev = await self.q.get()
                        if ev is None:
                            return
                        yield ev

            prov = Provider()

            class Socket:
                async def accept(self): pass

                async def send_text(self, text):
                    frames.append(json.loads(text))

                async def receive(self):
                    return {"text": json.dumps(await inbox.get())}

                async def close(self): pass

            gates = {}

            async def ask(req, conv_sid, brain, key=""):
                n = len(asks)
                asks.append(req)
                gate = gates.setdefault(n, asyncio.Event())
                await gate.wait()
                return answers[n]

            namespace = dict(
                asyncio=asyncio, json=json, sys=sys, WebSocket=Socket, Query=lambda x: x,
                cfgmod=types.SimpleNamespace(gate_active=lambda: False,
                                             read_settings=lambda: {"voice": {"live_provider": "chatgpt"}}),
                voice_live=types.SimpleNamespace(
                    make_provider=lambda cfg, recognition_lang="vi-VN", memory_index="": prov, MEMORY_CHARS=4000,
                    is_followup_ack=voice_live.is_followup_ack, followup_request=voice_live.followup_request,
                    is_noop_result=voice_live.is_noop_result, FOLLOWUP_ACK=voice_live.FOLLOWUP_ACK,
                    is_same_request=voice_live.is_same_request),
                openai_oauth=types.SimpleNamespace(write_codex_auth=lambda: None),
                _brain_memory_dir=lambda root: Path(directory), _brain_root=lambda b: directory,
                _fit_memory_index=lambda mem, cap=None: mem[:cap],
                _voice_ask_javis=ask, get_store=lambda: store, _brain_key=lambda b: b,
                voice_call=types.SimpleNamespace(live_settings=lambda c: c))
            exec(compile(_route(), "live-route", "exec"), namespace)
            route = asyncio.ensure_future(namespace["voice_live_ws"](Socket(), sid, "brain", "vi-VN"))

            async def until(cond, what):
                for _ in range(200):
                    if cond():
                        return
                    await asyncio.sleep(0.01)
                self.fail("chờ quá lâu: " + what)

            def release(n):
                gates.setdefault(n, asyncio.Event()).set()

            try:
                await script(prov, types.SimpleNamespace(until=until, release=release, asks=asks, frames=frames, inbox=inbox))
            finally:
                await inbox.put({"type": "stop"})
                await prov.q.put(None)
                for gate in gates.values():
                    gate.set()
                await asyncio.wait_for(route, 5)
            return prov, frames, asks, [m for m in store.get_messages(sid)]

    async def test_ack_followup_runs_brain_once_and_readback_is_not_a_bubble(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Kiểm tra số tiền trên TTS Dropship"}})
            await h.until(lambda: len(h.asks) == 1, "bộ não chạy việc đầu")
            await prov.q.put({"type": "transcript", "role": "user", "text": "Ok, xem xong kiểm tra xong thì báo anh nhé",
                              "final": True})
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Ok, xem xong kiểm tra xong thì báo anh nhé"}})
            await h.until(lambda: "h2" in prov.acks, "xác nhận câu nói thêm")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "trả kết quả cho model")
            # Model đọc lại kết quả: lời này không được thành bong bóng thứ hai.
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Dạ em đọc được rồi anh. ", "final": False})
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Hoa hồng là 21 triệu.", "final": False})
            await prov.q.put({"type": "turn_done"})
            # Người dùng nói tiếp: lời đáp sau đó hiện như thường.
            await prov.q.put({"type": "transcript", "role": "user", "text": "Cảm ơn em", "final": True})
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Dạ không có gì ạ.", "final": False})
            await prov.q.put({"type": "turn_done"})
            await h.until(lambda: sum(f["type"] == "turn_done" for f in h.frames) == 2, "hai lượt xong")

        prov, frames, asks, saved = await self._run(script, ["- Hoa hồng đã về: **21.234.050 đ**"])
        self.assertEqual(len(asks), 1, "câu nói thêm kiểu xác nhận không chạy bộ não chính lần nữa")
        self.assertEqual(prov.acks, ["h2"])
        self.assertEqual([cid for cid, _ in prov.results], ["h1"])
        self.assertEqual(sum(f["type"] == "tool_result" for f in frames), 1, "đúng một bong bóng kết quả")
        said = [f["text"] for f in frames if f["type"] == "transcript" and f.get("role") == "assistant"]
        self.assertEqual(said, ["Dạ không có gì ạ."], "lời đọc lại kết quả không thành bong bóng thứ hai")
        javis = [m["content"] for m in saved if m["role"] == "assistant"]
        self.assertEqual(javis, ["- Hoa hồng đã về: **21.234.050 đ**", "Dạ không có gì ạ."])

    async def test_typed_text_after_result_shows_the_reply(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis", "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả")
            await h.inbox.put({"type": "text", "text": "còn tháng trước?"})
            await asyncio.sleep(0.05)
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Để em xem nhé.", "final": False})
            await prov.q.put({"type": "turn_done"})
            await h.until(lambda: any(f["type"] == "turn_done" for f in h.frames), "lượt xong")

        prov, frames, asks, saved = await self._run(script, ["Doanh thu 12 triệu."])
        said = [f["text"] for f in frames if f["type"] == "transcript" and f.get("role") == "assistant"]
        self.assertEqual(said, ["Để em xem nhé."], "gõ chữ trong lúc gọi: lời đáp sau đó vẫn hiện")

    async def test_real_followup_runs_after_first_with_context(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "thêm cả số đơn huỷ nữa"}})
            await asyncio.sleep(0.05)
            self.assertEqual(len(h.asks), 1, "việc nói thêm chờ việc đầu xong, không chạy song song")
            h.release(0)
            await h.until(lambda: len(h.asks) == 2, "việc nói thêm chạy sau")
            h.release(1)
            await h.until(lambda: len(prov.results) == 2, "hai kết quả")

        prov, frames, asks, saved = await self._run(script, ["Doanh thu 12 triệu.", "Hôm nay có 3 đơn huỷ."])
        self.assertIn("Doanh thu hôm nay", asks[1])
        self.assertIn("thêm cả số đơn huỷ nữa", asks[1])
        self.assertIn(voice_live.FOLLOWUP_NOOP, asks[1])
        self.assertEqual([cid for cid, _ in prov.results], ["h1", "h2"])
        self.assertEqual([f["text"] for f in frames if f["type"] == "tool_result"],
                         ["Doanh thu 12 triệu.", "Hôm nay có 3 đơn huỷ."])

    async def test_duplicate_handoff_of_running_request_runs_brain_once(self):
        async def script(prov, h):
            q = "Javis ơi, xem giúp anh trong brain có những ghi chú nào"
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis", "args": {"request": q}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis", "args": {"request": q}})
            await h.until(lambda: "h2" in prov.acks, "handoff lặp được đóng")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả")

        prov, frames, asks, saved = await self._run(script, ["Có 7 ghi chú."])
        self.assertEqual(len(asks), 1, "model bắn handoff đôi cho cùng câu: bộ não chỉ chạy một lần")

    async def test_followup_noop_result_is_silent(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "vậy hả, để anh ngồi chờ"}})
            await asyncio.sleep(0.05)
            h.release(0)
            await h.until(lambda: len(h.asks) == 2, "việc nói thêm chạy sau")
            h.release(1)
            await h.until(lambda: "h2" in prov.acks, "xác nhận không có việc mới")

        prov, frames, asks, saved = await self._run(script, ["Doanh thu 12 triệu.", "JAVIS_NOOP"])
        self.assertEqual([cid for cid, _ in prov.results], ["h1"], "JAVIS_NOOP không được đọc ra loa")
        self.assertEqual([f["text"] for f in frames if f["type"] == "tool_result"], ["Doanh thu 12 triệu."])
        self.assertFalse(any("JAVIS_NOOP" in m["content"] for m in saved), "JAVIS_NOOP không vào lịch sử")
        running = sum(f["type"] == "tool" and f.get("status") == "running" for f in frames)
        done = sum(f["type"] == "tool" and f.get("status") == "done" for f in frames)
        self.assertEqual(running, done, "thanh gọi không kẹt ở Đang làm việc")

    async def test_request_after_result_is_a_new_task(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis", "args": {"request": "ok báo anh nhé"}})
            await h.until(lambda: len(h.asks) == 2, "việc mới")
            h.release(1)
            await h.until(lambda: len(prov.results) == 2, "kết quả hai")

        prov, frames, asks, saved = await self._run(script, ["Doanh thu 12 triệu.", "Dạ."])
        self.assertEqual(asks[1], "ok báo anh nhé", "việc đã xong thì câu sau là việc mới, không ghép ngữ cảnh")


if __name__ == "__main__":
    unittest.main()
