"""ChatGPT Live không lặp câu trả lời (0.65.21). Không mạng, không Codex thật.

    python tests/run.py voice_live_followup

Lỗi chủ dự án báo 01/10/2026 (tái hiện được trên dashboard thật): đang chờ Javis làm việc, người dùng
nói thêm "Ok, xem xong kiểm tra xong thì báo anh nhé". Model nói chuyện coi câu đó là một lần giao
việc nữa (Codex coi handoff tới giữa chừng là lời CHỈNH HƯỚNG việc đang chạy), Javis chạy bộ não chính
lần hai, ra hai bong bóng kết quả khác chữ, rồi lời đọc lại tóm tắt thành bong bóng thứ ba. Khoá:
  - câu nói thêm chỉ là xác nhận/nhắc báo: không chạy bộ não lần nữa, không bong bóng;
  - câu nói thêm có yêu cầu thật: chạy SONG SONG với việc đang chạy (0.71.2; trước đó xếp hàng chờ việc
    đầu xong, nên hỏi giữa chừng im re mấy phút), kèm việc đang chạy làm ngữ cảnh;
    bộ não trả JAVIS_NOOP thì không bong bóng, không đọc;
  - lời model đọc lại kết quả (đã có bong bóng đầy đủ) không thành bong bóng thứ hai, không vào lịch sử;
  - lời Javis sau khi người dùng nói tiếp vẫn hiện như thường.
Câu hỏi tiến độ và lời tự lên tiếng khi việc chạy lâu nằm ở test_voice_live_progress.py.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import unittest

import voice_live
from _live_route import LiveRouteMixin


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

    def test_noop_result(self):
        self.assertTrue(voice_live.is_noop_result("JAVIS_NOOP"))
        self.assertTrue(voice_live.is_noop_result("`JAVIS_NOOP`\n"))
        self.assertFalse(voice_live.is_noop_result("Số đơn huỷ hôm nay là 3. " * 10 + "JAVIS_NOOP"))
        self.assertFalse(voice_live.is_noop_result("Số đơn huỷ hôm nay là 3."))

    def test_chatgpt_ack_is_silent_and_prompt_says_no_redelegation(self):
        self.assertIn("đang chờ", voice_live.CHATGPT_LIVE_PROMPT)
        live = voice_live.ChatGPTLive(app_server_getter=lambda: None)
        asyncio.run(live.send_tool_ack("h2", "ask_javis", "x"))   # không gọi app-server nào


def acked(prov, cid):
    return any(c == cid for c, _ in prov.acks)


class LiveRouteFollowupTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    async def test_ack_followup_runs_brain_once_and_readback_is_not_a_bubble(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Kiểm tra số tiền trên TTS Dropship"}})
            await h.until(lambda: len(h.asks) == 1, "bộ não chạy việc đầu")
            await prov.q.put({"type": "transcript", "role": "user", "text": "Ok, xem xong kiểm tra xong thì báo anh nhé",
                              "final": True})
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Ok, xem xong kiểm tra xong thì báo anh nhé"}})
            await h.until(lambda: acked(prov, "h2"), "xác nhận câu nói thêm")
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

        prov, frames, asks, saved = await self.run_route(script, ["- Hoa hồng đã về: **21.234.050 đ**"])
        self.assertEqual(len(asks), 1, "câu nói thêm kiểu xác nhận không chạy bộ não chính lần nữa")
        self.assertEqual([c for c, _ in prov.acks], ["h2"])
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

        prov, frames, asks, saved = await self.run_route(script, ["Doanh thu 12 triệu."])
        said = [f["text"] for f in frames if f["type"] == "transcript" and f.get("role") == "assistant"]
        self.assertEqual(said, ["Để em xem nhé."], "gõ chữ trong lúc gọi: lời đáp sau đó vẫn hiện")

    async def test_real_followup_runs_alongside_first_with_context(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "thêm cả số đơn huỷ nữa"}})
            # Từ 0.71.2: không chờ việc đầu. Trước đó câu này nằm im tới khi việc đầu xong.
            await h.until(lambda: len(h.asks) == 2, "việc nói thêm chạy song song, không chờ việc đầu")
            h.release(0)
            h.release(1)
            await h.until(lambda: len(prov.results) == 2, "hai kết quả")

        prov, frames, asks, saved = await self.run_route(script, ["Doanh thu 12 triệu.", "Hôm nay có 3 đơn huỷ."])
        self.assertIn("Doanh thu hôm nay", asks[1])
        self.assertIn("thêm cả số đơn huỷ nữa", asks[1])
        self.assertIn(voice_live.FOLLOWUP_NOOP, asks[1])
        self.assertEqual(sorted(cid for cid, _ in prov.results), ["h1", "h2"])
        self.assertEqual(sorted(f["text"] for f in frames if f["type"] == "tool_result"),
                         ["Doanh thu 12 triệu.", "Hôm nay có 3 đơn huỷ."])

    async def test_duplicate_handoff_of_running_request_runs_brain_once(self):
        async def script(prov, h):
            q = "Javis ơi, xem giúp anh trong brain có những ghi chú nào"
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis", "args": {"request": q}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis", "args": {"request": q}})
            await h.until(lambda: acked(prov, "h2"), "handoff lặp được đóng")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả")

        prov, frames, asks, saved = await self.run_route(script, ["Có 7 ghi chú."])
        self.assertEqual(len(asks), 1, "model bắn handoff đôi cho cùng câu: bộ não chỉ chạy một lần")

    async def test_followup_noop_result_is_silent(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay"}})
            await h.until(lambda: len(h.asks) == 1, "việc đầu")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "vậy hả, để anh ngồi chờ"}})
            await h.until(lambda: len(h.asks) == 2, "việc nói thêm chạy song song")
            h.release(1)
            await h.until(lambda: acked(prov, "h2"), "xác nhận không có việc mới")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả việc đầu")

        prov, frames, asks, saved = await self.run_route(script, ["Doanh thu 12 triệu.", "JAVIS_NOOP"])
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

        prov, frames, asks, saved = await self.run_route(script, ["Doanh thu 12 triệu.", "Dạ."])
        self.assertEqual(asks[1], "ok báo anh nhé", "việc đã xong thì câu sau là việc mới, không ghép ngữ cảnh")


if __name__ == "__main__":
    unittest.main()
