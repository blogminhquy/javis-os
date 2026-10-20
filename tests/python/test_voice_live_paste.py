"""A file pasted in the chat during a Live call gets ONE brain turn and ONE voice (0.236.0). No network.

    python tests/run.py voice_live_paste

Owner report 2026-10-19: in Live mode, pasting an image opened an ordinary chat turn (read aloud by the Edge voice,
in Vietnamese) while the Live model, told "look at this picture", handed the same picture to ask_javis (a second
brain turn, spoken in English). Two answers over each other. The contract now:
  - the dashboard sends the message as an "ask" frame on /ws/voice-live, no chat turn of its own;
  - the route stores the full message (F5 rebuilds the image bubble from it), runs the brain ONCE and has the Live
    model read the answer;
  - while that runs, and a short while after, an ask_javis about the image is acknowledged, not run again;
  - the reply language falls back to the configured one when the spoken line gives none.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import unittest

import voice_live
from _live_route import LiveRouteMixin, DeferringProvider

FULL = ("[File đính kèm để ĐỌC (đường dẫn):\n- /brain/attachments/mi-sot.png\nMặc định: chỉ đọc file rồi trả lời.]"
        "\n\nxem giúp anh ảnh này")


class AttachmentWordsTests(unittest.TestCase):
    def test_is_about_attachment(self):
        for text in ("Look at the image the user pasted", "xem giúp anh ảnh này", "đọc file anh vừa gửi",
                     "Describe the screenshot", "what is in this picture"):
            self.assertTrue(voice_live.is_about_attachment(text), text)
        for text in ("", "doanh thu hôm nay bao nhiêu", "xem lịch tuần này"):
            self.assertFalse(voice_live.is_about_attachment(text), text)
        self.assertTrue(voice_live.is_about_attachment("open mi-sot.png", ["mi-sot.png"]), "a file name counts")

    def test_readback_text(self):
        t = voice_live.readback_text("Ảnh là **mì** và sốt.")
        self.assertTrue(t.startswith(voice_live.LATE_RESULT_TAG))
        self.assertIn("không gọi ask_javis", t)
        self.assertIn("mì", t)
        self.assertNotIn("**", t, "markdown is stripped before speech")
        self.assertNotIn("—", voice_live.ATTACHMENT_ACK + t)

    def test_providers_have_a_readback(self):
        # Every provider can read an answer it did not ask for; the webrtc ones use their own channels.
        self.assertIsNot(voice_live.GPTLive.read_result, voice_live.LiveProvider.read_result)
        self.assertIsNot(voice_live.ChatGPTLive.read_result, voice_live.LiveProvider.read_result)
        live = voice_live.ChatGPTLive(app_server_getter=lambda: None)
        queued = []
        live._enqueue_speech = queued.append
        asyncio.run(live.read_result("Ảnh là mì."))
        self.assertEqual(queued, ["Ảnh là mì."], "ChatGPT Live speaks it from the speech queue")


class LivePasteRouteTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    async def test_one_brain_turn_and_the_model_reads_it(self):
        async def script(prov, h):
            await h.inbox.put({"type": "ask", "text": FULL, "display": "xem giúp anh ảnh này",
                               "files": ["mi-sot.png"]})
            await h.until(lambda: len(h.asks) == 1, "the brain runs the pasted file")
            # The Live model hears "look at this image" and tries to hand the same file over again.
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis",
                              "args": {"request": "Look at the image the user just pasted"}})
            await h.until(lambda: any(c == "c1" for c, _ in prov.acks), "the duplicate is acknowledged")
            h.release(0)
            await h.until(lambda: prov.readbacks, "the model reads the answer")
            # Right after the answer, the same question again is still that file.
            await prov.q.put({"type": "tool_call", "id": "c2", "name": "ask_javis",
                              "args": {"request": "Describe the picture"}})
            await h.until(lambda: any(c == "c2" for c, _ in prov.acks), "the late duplicate is acknowledged too")
            # A real new request still goes through.
            await prov.q.put({"type": "tool_call", "id": "c3", "name": "ask_javis",
                              "args": {"request": "doanh thu hôm nay bao nhiêu"}})
            await h.until(lambda: len(h.asks) == 2, "a new request runs")
            h.release(1)
            await h.until(lambda: prov.results, "its answer is returned")

        prov, frames, asks, saved = await self.run_route(script, ["Ảnh là mì và sốt.", "10 triệu"])
        self.assertEqual(asks[0], FULL, "the brain gets the whole message, file block included")
        self.assertEqual(len(asks), 2)
        self.assertEqual(prov.readbacks, ["Ảnh là mì và sốt."])
        self.assertTrue(all(t == voice_live.ATTACHMENT_ACK for _, t in prov.acks))
        users = [m["content"] for m in saved if m["role"] == "user"]
        self.assertIn(FULL, users, "the stored message keeps the file block so F5 shows the image")
        bubbles = [f["text"] for f in frames if f["type"] == "tool_result"]
        self.assertEqual(bubbles[0], "Ảnh là mì và sốt.")
        self.assertEqual(sum(f == {"type": "tool", "name": "ask_javis", "status": "running"} for f in frames), 2)

    async def test_reply_language_falls_back_to_the_configured_one(self):
        async def script(prov, h):
            await h.inbox.put({"type": "ask", "text": FULL, "display": "", "files": []})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            self.assertTrue(h.langs[0], "a reply language is always pinned")
            h.release(0)
            await h.until(lambda: prov.readbacks, "read out")

        await self.run_route(script, ["ok"])

    def test_live_call_lang_helper(self):
        import ast
        import types
        tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_live_call_lang")
        ns = {"lang_mod": types.SimpleNamespace(call_language=lambda said, rl="": ""),
              "localefmt": types.SimpleNamespace(ngon_ngu_tra_loi=lambda: "vi")}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "h", "exec"), ns)
        self.assertEqual(ns["_live_call_lang"]("", "auto"), "vi", "auto mic, nothing said: configured language")
        ns["lang_mod"] = types.SimpleNamespace(call_language=lambda said, rl="": "en")
        self.assertEqual(ns["_live_call_lang"]("hello", "auto"), "en", "a detected language still wins")

    async def test_deferring_provider_reads_it_too(self):
        self.provider_class = DeferringProvider

        async def script(prov, h):
            await h.inbox.put({"type": "ask", "text": FULL, "display": "xem ảnh", "files": ["mi-sot.png"]})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            h.release(0)
            await h.until(lambda: prov.readbacks, "Gemini-shaped provider reads it out")

        prov, _f, _a, _s = await self.run_route(script, ["ok"])
        self.assertEqual(prov.late, [], "not sent as a late tool result: nobody called a tool")


class SourceCanaries(unittest.TestCase):
    def test_route_and_dashboard(self):
        main = (SERVER / "main.py").read_text(encoding="utf-8")
        self.assertIn('d.get("type") == "ask"', main)
        self.assertIn("[voice live] bỏ ask_javis trùng", main, "a blocked duplicate leaves a log line")
        self.assertNotIn("call_lang=lang_mod.call_language(", main, "every Live brain turn uses the fallback")
        app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("window.JavisVoiceLive.ask(liveMsg", app, "a paste during Live goes through the ask frame")
        js = (ROOT / "dashboard" / "voice-live.js").read_text(encoding="utf-8")
        self.assertIn('type: "ask"', js)
        self.assertIn("ask: ask", js)


if __name__ == "__main__":
    unittest.main()
