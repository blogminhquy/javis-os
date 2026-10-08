"""Cuộc gọi giọng nói giữ đúng thứ tiếng người dùng nói, kể cả khi câu giao việc là tiếng Anh (0.85.10).

    python tests/run.py voice_giu_ngon_ngu      (KHÔNG mạng)

Lỗi thật, khách báo 08/10/2026 kèm ảnh: đang gọi ChatGPT Live bằng tiếng Việt ("Anh vừa mới gửi
em cái link Drive ở trên đó, kiểm tra lại phần tin nhắn đi"), câu trả lời của bộ não chính lại ra
tiếng Anh ("The contract does not match a 2-week trial..."), rồi Live đọc to câu tiếng Anh nên
nghe như đổi giọng giữa cuộc gọi.

Gốc: câu giao việc cho bộ não chính (`input_transcript` của handoff) là câu model giọng nói TỰ
DIỄN ĐẠT LẠI, có lúc bằng tiếng Anh. Bộ não chính để model tự bám theo thứ tiếng của tin nhắn
cuối, mà tin nhắn cuối chính là câu tiếng Anh đó.

Sửa: lượt từ cuộc gọi ghim ngôn ngữ trả lời theo câu người dùng VỪA NÓI (dò ra thì theo đó,
không dò ra thì theo ngôn ngữ nhận dạng của mic), ở bậc "mặc định của kênh". Người dùng ra lệnh
thẳng trong câu, hoặc đã ghim ngôn ngữ ở Cài đặt, thì vẫn thắng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import sys
import unittest

import lang
import voice_live
from _live_route import LiveRouteMixin

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VI = "Anh vừa mới gửi em cái link Drive ở trên đó, kiểm tra lại phần tin nhắn đi"
EN_HANDOFF = "Check the Google Drive link the user sent earlier in the chat and review the contract"


def _n(method, **params):
    return {"method": method, "params": params}


class CallLanguage(unittest.TestCase):
    def test_follows_what_the_person_said(self):
        self.assertEqual(lang.call_language(VI, "vi-VN"), "vi")
        self.assertEqual(lang.call_language("Can you check the revenue for this week", "vi-VN"), "en",
                         "người dùng nói tiếng Anh thật thì trả lời tiếng Anh")

    def test_falls_back_to_the_mic_language(self):
        self.assertEqual(lang.call_language("", "vi-VN"), "vi")
        self.assertEqual(lang.call_language("ok", "en-US"), "en")
        self.assertEqual(lang.call_language("", "auto"), "", "mic để auto mà không nghe ra thì không ghim")

    def test_pin_beats_the_english_handoff_but_not_the_owner(self):
        # Đúng như bộ não chính thấy: tin nhắn cuối là câu handoff tiếng Anh.
        qd = lang.resolve(turn_text=EN_HANDOFF, channel_default=lang.call_language(VI, "vi-VN"))
        self.assertEqual(qd.lang, "vi")
        self.assertFalse(qd.theo_nguoi_dung, "không để model bám theo câu handoff tiếng Anh")
        self.assertIn("Ngôn ngữ trả lời", lang.khoi_ngon_ngu(qd))
        owner = lang.resolve(turn_text=EN_HANDOFF, reply_pref="en", channel_default="vi")
        self.assertEqual(owner.lang, "en", "ngôn ngữ ghim ở Cài đặt vẫn thắng")
        asked = lang.resolve(turn_text="trả lời bằng tiếng Anh nhé", channel_default="vi")
        self.assertEqual(asked.lang, "en", "lệnh thẳng trong câu vẫn thắng")

    def test_engine_reads_the_pin_from_meta(self):
        src = (SERVER / "main.py").read_text(encoding="utf-8")
        self.assertIn('channel_default=(_ngon_ngu_cuoc_goi(meta) or ("vi" if channel == "zalo" and not bot else ""))', src)
        self.assertIn('meta={"chat_id": key, "call_lang": call_lang}', src)


class HandoffCarriesSpeech(unittest.TestCase):
    def test_handoff_keeps_what_the_person_said(self):
        tp = voice_live.ChatGPTLive(app_server_getter=lambda: None)
        evs = []
        for m in (_n("thread/realtime/transcript/delta", role="user", delta=VI),
                  _n("thread/realtime/itemAdded", item={"type": "handoff_request", "handoff_id": "h1",
                                                         "input_transcript": EN_HANDOFF})):
            evs += tp.translate(m)
        call = next(e for e in evs if e["type"] == "tool_call")
        self.assertEqual(call["args"]["request"], EN_HANDOFF, "yêu cầu vẫn là câu model giao")
        self.assertEqual(call["said"], VI, "kèm câu người dùng thật sự nói")


class RoutePinsTheSpokenLanguage(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    async def test_vietnamese_speech_english_handoff(self):
        async def script(prov, h):
            await prov.q.put({"type": "transcript", "role": "user", "text": VI, "final": True})
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": EN_HANDOFF}, "said": VI})
            await h.until(lambda: len(h.asks) == 1, "bộ não chính được gọi")
            self.assertEqual(h.langs, ["vi"])
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả")

        await self.run_route(script, ["Hợp đồng không khớp gói thử 2 tuần."])

    async def test_english_speech_stays_english(self):
        async def script(prov, h):
            said = "Can you check the contract in the Drive link I sent"
            await prov.q.put({"type": "transcript", "role": "user", "text": said, "final": True})
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": EN_HANDOFF}})
            await h.until(lambda: len(h.asks) == 1, "bộ não chính được gọi")
            self.assertEqual(h.langs, ["en"], "không có `said` thì lấy câu đã chốt gần nhất")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "kết quả")

        await self.run_route(script, ["The contract runs 18 months."])


if __name__ == "__main__":
    unittest.main(verbosity=2)
