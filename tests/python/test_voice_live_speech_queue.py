"""ChatGPT Live đọc kết quả LẦN LƯỢT (0.65.23). Không mạng, không Codex thật.

    python tests/run.py voice_live_speech_queue

Lỗi chủ dự án báo 01/10 (máy tính, một tab): hai câu trả lời liền nhau bị đọc chồng, lẫn vào nhau,
không lần lượt. Đo trên Codex 0.153.4 và 0.158: kết quả thứ hai đẩy vào (`appendSpeech`) giữa lúc
model đang nói thì nó TRỘN hai nội dung vào cùng một lượt nói. Từ 0.65.21 câu nói thêm chạy sau
việc đầu nên kết quả thứ hai hay tới đúng lúc đang đọc kết quả thứ nhất. Khoá:
  - model đang im: kết quả đọc ngay;
  - model đang nói (lời đệm, lời đáp hay lời đọc kết quả trước): kết quả chờ tới khi lượt đó xong;
  - vừa đẩy một kết quả mà model chưa kịp mở lời: kết quả sau vẫn chờ (một khoảng ân hạn);
  - không bao giờ kẹt: chờ quá trần thì vẫn đọc; send_tool_result không chặn route;
  - cúp máy thì bỏ các lời đọc còn trong hàng.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import time
import unittest

import voice_live


class FakeServer:
    def __init__(self):
        self.calls = []
        self.queue = None

    async def request(self, method, params=None, timeout=30.0):
        self.calls.append((time.monotonic(), method, params or {}))
        if method == "thread/start":
            return {"thread": {"id": "th-1"}}
        return {}

    def subscribe(self, thread_id):
        self.queue = asyncio.Queue()
        return self.queue

    def unsubscribe(self, thread_id):
        pass

    def push(self, method, **params):
        params.setdefault("threadId", "th-1")
        self.queue.put_nowait({"method": method, "params": params})

    def spoken(self):
        return [p["text"] for _, m, p in self.calls if m == "thread/realtime/appendSpeech"]


class SpeechQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeServer()

        async def getter():
            return self.fake

        self.prov = voice_live.ChatGPTLive(app_server_getter=getter)
        self.prov.SPEECH_START_GRACE = 0.3
        self.prov.SPEECH_GAP = 0.05
        self.prov.SPEECH_WAIT_MAX = 2.0
        self.prov.SPEECH_STALL = 1.0
        await self.prov.connect()
        self.events = []

        async def drain():
            async for ev in self.prov.events():
                self.events.append(ev)

        self.reader = asyncio.ensure_future(drain())

    async def asyncTearDown(self):
        await self.prov.close()
        self.reader.cancel()

    async def until(self, cond, timeout=2.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            await asyncio.sleep(0.01)
        return cond()

    def speak(self, delta):
        self.fake.push("thread/realtime/transcript/delta", role="assistant", delta=delta)

    def done(self, text="x"):
        self.fake.push("thread/realtime/transcript/done", role="assistant", text=text)

    async def test_idle_model_reads_at_once(self):
        t0 = time.monotonic()
        await self.prov.send_tool_result("h1", "ask_javis", "Doanh thu hôm nay 12 triệu.")
        self.assertLess(time.monotonic() - t0, 0.1, "send_tool_result không chặn route")
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Doanh thu hôm nay 12 triệu."], 0.3))

    async def test_second_result_waits_for_the_current_readback(self):
        await self.prov.send_tool_result("h1", "ask_javis", "Kết quả một.")
        self.assertTrue(await self.until(lambda: len(self.fake.spoken()) == 1))
        self.speak(" Dạ, kết quả một")   # model bắt đầu đọc kết quả thứ nhất
        await asyncio.sleep(0.05)
        t0 = time.monotonic()
        await self.prov.send_tool_result("h2", "ask_javis", "Kết quả hai.")
        self.assertLess(time.monotonic() - t0, 0.1, "send_tool_result không chặn route dù đang đọc")
        await asyncio.sleep(0.5)
        self.assertEqual(self.fake.spoken(), ["Kết quả một."], "đang đọc thì kết quả hai phải chờ")
        self.done(" Dạ, kết quả một.")
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Kết quả một.", "Kết quả hai."]),
                        "đọc xong lượt trước thì mới đọc kết quả hai")

    async def test_waits_while_the_model_answers_the_user(self):
        self.speak(" Dạ, để em kiểm tra luôn ạ")   # lời đáp của chính model, chưa xong
        await asyncio.sleep(0.05)
        await self.prov.send_tool_result("h1", "ask_javis", "Kết quả.")
        await asyncio.sleep(0.3)
        self.assertEqual(self.fake.spoken(), [], "không chen vào giữa câu model đang nói")
        self.done()
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Kết quả."]))

    async def test_grace_after_push_before_the_model_starts(self):
        await self.prov.send_tool_result("h1", "ask_javis", "Một.")
        await self.prov.send_tool_result("h2", "ask_javis", "Hai.")
        await asyncio.sleep(0.1)
        self.assertEqual(self.fake.spoken(), ["Một."], "model chưa kịp mở lời cho kết quả một thì chưa đẩy kết quả hai")
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Một.", "Hai."], 1.0),
                        "model không nói gì sau ân hạn thì vẫn đọc tiếp")

    async def test_interrupted_turn_without_done_does_not_block(self):
        self.speak(" Dạ kết quả một")    # người dùng chen ngang: model im, không có done
        await self.prov.send_tool_result("h1", "ask_javis", "Kết quả hai.")
        await asyncio.sleep(0.5)
        self.assertEqual(self.fake.spoken(), [], "còn trong khoảng có thể đang nói")
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Kết quả hai."], 1.5),
                        "lâu không có chữ mới thì coi model đã im, đọc tiếp")

    async def test_never_stuck(self):
        self.prov.SPEECH_STALL = 60.0   # chỉ còn trần SPEECH_WAIT_MAX cứu
        self.speak(" Dạ")   # lượt nói không bao giờ có done (mất khung)
        await self.prov.send_tool_result("h1", "ask_javis", "Kết quả.")
        await asyncio.sleep(0.3)
        self.assertEqual(self.fake.spoken(), [])
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Kết quả."], 3.0), "chờ quá trần thì vẫn đọc")

    async def test_hang_up_drops_pending_speech(self):
        self.speak(" Dạ đang đọc")
        await self.prov.send_tool_result("h1", "ask_javis", "Kết quả.")
        await self.prov.close()
        await asyncio.sleep(0.5)
        self.assertEqual(self.fake.spoken(), [], "cúp máy thì không đọc nốt")


if __name__ == "__main__":
    unittest.main()
