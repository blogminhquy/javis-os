"""Gemini 3.1 Live no longer freezes while the main brain works (0.220.0). No network.

    python tests/run.py voice_live_deferred

Gemini 3.1 Flash Live cannot run a tool in the background: until the tool answers, the model says
nothing and hears nothing useful. ask_javis runs a whole brain turn (5 to 60 seconds), so the call
froze. Now the route answers the call at once (DEFERRED_ACK) and delivers the brain's result later,
waiting for a pause first. Gemini 2.5 (NON_BLOCKING) and the other providers are unchanged.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import time
import unittest

import voice_live
from _live_route import DeferringProvider, LiveRouteMixin


class GeminiProviderTests(unittest.TestCase):
    def test_31_defers_and_25_does_not(self):
        g31 = voice_live.GeminiLive("k", model="gemini-3.1-flash-live-preview")
        g25 = voice_live.GeminiLive("k", model="gemini-2.5-flash-native-audio-preview-12-2025")
        self.assertTrue(g31.defers_tool_results())
        self.assertFalse(g25.defers_tool_results())
        self.assertIn(voice_live.LATE_RESULT_TAG, g31.system, "3.1 is told what the tagged turns are")
        self.assertNotIn(voice_live.LATE_RESULT_TAG, g25.system)
        self.assertFalse(voice_live.OpenAIRealtime("k").defers_tool_results())

    def test_late_result_is_a_tagged_user_turn(self):
        g = voice_live.GeminiLive("k", model="gemini-3.1-flash-live-preview")
        msg = g.late_result_messages("Doanh thu hôm nay 12 triệu.")[0]["clientContent"]
        text = msg["turns"][0]["parts"][0]["text"]
        self.assertTrue(msg["turnComplete"])
        self.assertTrue(text.startswith(voice_live.LATE_RESULT_TAG) and "12 triệu" in text)

    def test_quiet_tracks_both_sides(self):
        g = voice_live.GeminiLive("k", model="gemini-3.1-flash-live-preview")
        self.assertTrue(g.is_quiet(), "nobody has spoken yet")
        g.translate({"serverContent": {"outputTranscription": {"text": "Để em xem"}}})
        self.assertFalse(g.is_quiet(), "the model is talking")
        g.translate({"serverContent": {"turnComplete": True}})
        g._model_at = time.monotonic() - 5
        self.assertTrue(g.is_quiet())
        g.translate({"serverContent": {"inputTranscription": {"text": "à mà"}}})
        self.assertFalse(g.is_quiet(), "the person just spoke")

    def test_prompts_carry_no_sample_filler(self):
        # A quoted sample is what the model repeats word for word, in the sample's language.
        self.assertNotIn("để mình xem", voice_live.ASK_JAVIS_TOOL["description"])
        self.assertIn("MỘT câu", voice_live.SYSTEM_PROMPT)


class DeferredRouteTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    provider_class = DeferringProvider

    async def test_call_is_answered_at_once_and_result_arrives_late(self):
        async def script(prov, h):
            prov.quiet = False   # the person is still talking when the result is ready
            await prov.q.put({"type": "tool_call", "id": "g1", "name": "ask_javis",
                              "args": {"request": "doanh thu hôm nay"}})
            await h.until(lambda: prov.results, "the tool call is answered before the brain runs")
            self.assertEqual(prov.results[0], ("g1", voice_live.DEFERRED_ACK))
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            h.release(0)
            await h.until(lambda: prov.waits, "the result waits for a pause")
            await asyncio.sleep(0.05)
            self.assertEqual(prov.late, [], "nothing is pushed while someone is talking")
            prov.quiet = True
            await h.until(lambda: prov.late, "the result is delivered once quiet")
            self.assertEqual(prov.late, ["Doanh thu hôm nay 12 triệu."])
            self.assertEqual(len(prov.results), 1, "the call id is answered exactly once")

        prov, frames, asks, saved = await self.run_route(script, ["Doanh thu hôm nay 12 triệu."])
        self.assertTrue(any(f.get("type") == "tool_result" for f in frames), "the full result still shows as a bubble")

    async def test_progress_question_answers_the_call_itself(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "g1", "name": "ask_javis",
                              "args": {"request": "tổng hợp email tuần này"}})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            await prov.q.put({"type": "tool_call", "id": "g2", "name": "ask_javis",
                              "args": {"request": "xong chưa em"}})
            await h.until(lambda: any(c == "g2" for c, _ in prov.acks), "the progress call gets its own answer")
            self.assertEqual(prov.status_calls, [], "a deferring provider must not leave g2 unanswered")
            h.release(0)
            await h.until(lambda: prov.late, "the first job still delivers")

        await self.run_route(script, ["Có 14 email."])


if __name__ == "__main__":
    unittest.main()
