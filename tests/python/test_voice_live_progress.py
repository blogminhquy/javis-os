"""ChatGPT Live stays answerable while the main brain runs a long job (0.71.2). No network.

    python tests/run.py voice_live_progress

Owner's call log, 2026-10-03: while Javis spent minutes writing a spec, every question the owner
asked ("is it done yet?", "can you hear me?", "read me the titles") got a stalled filler line
("I'm on it"). The question at 17:45 was answered at 17:56. Cause: since 0.65.21 every `ask_javis`
handoff of a call waited on ONE lock, so a follow-up could not start until the long job ended, and
then the queued follow-ups ran one by one and their stale answers were read out in a burst.

This file pins the fix:
  - a progress question while a job runs is answered at once from the real state (what runs, for how
    long, which step) and never reaches the brain;
  - a real new request runs alongside the running one instead of waiting for it;
  - a job that runs long makes Javis speak up on its own, only when nobody is talking, and the
    status line is neither a chat bubble nor part of the saved history;
  - a status line that is still queued when the real result arrives is dropped, so it is never
    read out after the answer it was waiting for.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import time
import unittest

import voice_live
from _live_route import LiveRouteMixin
from test_voice_live_speech_queue import FakeServer

# Real questions from the owner's call (speech-to-text output, punctuation and all).
PROGRESS_QUESTIONS = (
    "Tiến độ spec đến đâu rồi? Thông báo lại giúp anh nhé",
    "Vẫn chưa xong à",
    "Em xong chỗ đấy chưa",
    "Vẫn đang làm spec chi tiết đúng không",
    "Mình đang làm nhiệm vụ nào? Nghe xem nào",
    "Bao nhiêu lâu thì hoàn thiện ấy",
    "Có nghe thấy tiếng anh nói không",
    "Xong chưa em",
    "Are you done yet?",
    "Can you hear me?",
)
# Requests that merely sound close: swallowing one of these would lose what the owner asked for.
REAL_REQUESTS = (
    "Doanh thu hôm nay là bao nhiêu",
    "Thêm cả số đơn huỷ nữa",
    "Anh chưa xong bài slide, em giúp anh phần mở đầu với",
    "Mở trang việc đi",
    "Ước lượng doanh thu tháng này giúp anh",
    "Ok, xong thì báo anh nhé",
    "Kiểm tra lịch tuần này rồi nhắn cho chị Lan xem anh còn rảnh buổi nào xong chưa thì báo lại luôn nhé",
    "Send the report to Lan",
)


class ProgressQuestionTests(unittest.TestCase):
    def test_owner_progress_questions_are_recognised(self):
        for text in PROGRESS_QUESTIONS:
            self.assertTrue(voice_live.is_progress_question(text), text)

    def test_requests_are_not_mistaken_for_progress_questions(self):
        for text in REAL_REQUESTS + ("", "   "):
            self.assertFalse(voice_live.is_progress_question(text), text)


class StatusLineTests(unittest.TestCase):
    def test_one_job_names_the_work_the_time_and_the_step(self):
        job = {"request": "Viết spec slide HTML cho buổi học Javis", "started": 100.0,
               "step": "⚙ Đang dùng công cụ: Write"}
        text = voice_live.status_line([job], now=350.0)   # 250 s = about 4 minutes
        self.assertIn("Viết spec slide HTML", text)
        self.assertIn("4", text)
        self.assertIn("Write", text)
        self.assertNotIn("⚙", text, "the step is spoken aloud: no symbols")

    def test_a_short_wait_is_told_in_seconds_and_a_missing_step_is_skipped(self):
        job = {"request": "Doanh thu hôm nay", "started": 10.0, "step": ""}
        text = voice_live.status_line([job], now=55.0)
        self.assertIn("45", text)
        self.assertNotIn("Đang dùng công cụ", text)

    def test_several_jobs_are_counted_and_the_oldest_sets_the_time(self):
        jobs = [{"request": "Làm slide", "started": 0.0, "step": ""},
                {"request": "Tính doanh thu", "started": 200.0, "step": ""}]
        text = voice_live.status_line(jobs, now=300.0)
        self.assertIn("2", text)
        self.assertIn("5", text, "the oldest job has run 300 s = 5 minutes")
        self.assertIn("Làm slide", text)
        self.assertIn("Tính doanh thu", text)

    def test_a_long_request_is_shortened_not_read_in_full(self):
        job = {"request": "Viết " + "rất dài " * 80, "started": 0.0, "step": ""}
        self.assertLess(len(voice_live.status_line([job], now=30.0)), 400)

    def test_parallel_request_carries_the_running_work_and_the_noop_way_out(self):
        text = voice_live.parallel_request(["Viết spec slide HTML"], "Thêm câu hỏi tự nhận thức")
        self.assertIn("Viết spec slide HTML", text)
        self.assertIn("Thêm câu hỏi tự nhận thức", text)
        self.assertIn(voice_live.FOLLOWUP_NOOP, text)
        self.assertIn("SONG SONG", text, "the brain must know the other job has NOT finished")


class StatusSpeechTests(unittest.IsolatedAsyncioTestCase):
    """ChatGPTLive.say_status: a spoken line that yields to real results."""

    async def asyncSetUp(self):
        self.fake = FakeServer()

        async def getter():
            return self.fake

        self.prov = voice_live.ChatGPTLive(app_server_getter=getter)
        self.prov.SPEECH_START_GRACE, self.prov.SPEECH_GAP = 0.3, 0.05
        self.prov.SPEECH_WAIT_MAX, self.prov.SPEECH_STALL = 2.0, 1.0
        await self.prov.connect()

        async def drain():
            async for _ in self.prov.events():
                pass

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

    async def test_status_is_spoken_when_the_model_is_idle(self):
        self.assertTrue(await self.prov.say_status("Em vẫn đang làm."))
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Em vẫn đang làm."]))

    async def test_a_status_still_queued_is_dropped_when_the_real_result_arrives(self):
        self.fake.push("thread/realtime/transcript/delta", role="assistant", delta=" Dạ, để em")
        await asyncio.sleep(0.05)   # the model is mid-sentence, so the status has to wait
        await self.prov.say_status("Em vẫn đang làm, được 2 phút.")
        await self.prov.send_tool_result("h1", "ask_javis", "Xong rồi anh, có 24 slide.")
        self.fake.push("thread/realtime/transcript/done", role="assistant", text="x")
        self.assertTrue(await self.until(lambda: self.fake.spoken() == ["Xong rồi anh, có 24 slide."]))
        await asyncio.sleep(0.3)
        self.assertEqual(self.fake.spoken(), ["Xong rồi anh, có 24 slide."],
                         "a stale 'still working' line must never follow the answer")

    async def test_not_quiet_while_the_user_is_mid_sentence_or_the_model_is_talking(self):
        self.assertTrue(self.prov.is_quiet())
        self.fake.push("thread/realtime/transcript/delta", role="user", delta="Em xong chỗ")
        await asyncio.sleep(0.05)
        self.assertFalse(self.prov.is_quiet(), "the user is talking")
        self.fake.push("thread/realtime/transcript/done", role="user", text="Em xong chỗ đấy chưa")
        await asyncio.sleep(0.05)
        self.fake.push("thread/realtime/transcript/delta", role="assistant", delta=" Dạ")
        await asyncio.sleep(0.05)
        self.assertFalse(self.prov.is_quiet(), "the model is talking")

    async def test_no_status_after_hang_up(self):
        await self.prov.close()
        self.assertFalse(await self.prov.say_status("Em vẫn đang làm."))
        await asyncio.sleep(0.2)
        self.assertEqual(self.fake.spoken(), [])


class LiveRouteProgressTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    async def test_progress_question_is_answered_from_state_and_never_reaches_the_brain(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML cho buổi học Javis"}})
            await h.until(lambda: len(h.asks) == 1, "first job running")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Vẫn chưa xong à"}})
            await h.until(lambda: len(prov.status_calls) == 1, "status spoken")
            await asyncio.sleep(0.05)
            self.assertEqual(len(h.asks), 1, "the progress question must not start a second brain run")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "result of the first job")

        prov, frames, asks, saved = await self.run_route(script, ["Xong, file ở exports."])
        self.assertIn("Viết spec slide HTML", prov.status_calls[0], "the status names the running work")
        self.assertEqual([cid for cid, _ in prov.results], ["h1"], "only the real job returns a result")
        self.assertEqual(sum(f["type"] == "tool_result" for f in frames), 1, "one bubble: the real result")
        self.assertEqual([m["content"] for m in saved if m["role"] == "assistant"], ["Xong, file ở exports."],
                         "answering a progress question writes no history entry of its own")

    async def test_the_models_own_filler_after_a_progress_question_is_not_swallowed(self):
        # Every handoff makes the model say a filler line of its own ("Dạ, đợi em xem ạ"). It arrives
        # right after the handoff, before the status line is read. If the route marked the NEXT model
        # turn as a hidden read-back at that moment, it would hide this filler and show the status.
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "first job running")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Vẫn chưa xong à"}})
            await h.until(lambda: len(prov.status_calls) == 1, "status handed to the model")
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Dạ, đợi em xem ạ.", "final": False})
            await prov.q.put({"type": "turn_done"})
            await h.until(lambda: any(f["type"] == "turn_done" for f in h.frames), "filler turn closed")

        prov, frames, asks, saved = await self.run_route(script, ["x"])
        said = [f["text"] for f in frames if f["type"] == "transcript" and f.get("role") == "assistant"]
        self.assertEqual(said, ["Dạ, đợi em xem ạ."], "the model's own words are shown as usual")

    async def test_the_current_step_is_part_of_the_status(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1 and h.progress.get(0), "first job running")
            await h.progress[0]("⚙ Đang dùng công cụ: Write")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Tiến độ đến đâu rồi"}})
            await h.until(lambda: len(prov.status_calls) == 1, "status spoken")

        prov, *_ = await self.run_route(script, ["x"])
        self.assertIn("Write", prov.status_calls[0])

    async def test_a_new_request_runs_alongside_the_running_job(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "first job running")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay là bao nhiêu"}})
            await h.until(lambda: len(h.asks) == 2, "second job started WITHOUT waiting for the first")
            h.release(1)   # the short job finishes first and is read out first
            await h.until(lambda: len(prov.results) == 1, "short job result")
            self.assertEqual(prov.results[0][0], "h2")
            h.release(0)
            await h.until(lambda: len(prov.results) == 2, "long job result")

        prov, frames, asks, saved = await self.run_route(script, ["Đã viết xong spec.", "Doanh thu 12 triệu."])
        self.assertIn("Viết spec slide HTML", asks[1], "the second job knows what is already running")
        self.assertIn("Doanh thu hôm nay là bao nhiêu", asks[1])
        self.assertEqual([cid for cid, _ in prov.results], ["h2", "h1"], "each result goes back to its own handoff")
        self.assertEqual([f["text"] for f in frames if f["type"] == "tool_result"],
                         ["Doanh thu 12 triệu.", "Đã viết xong spec."])

    async def test_parallel_jobs_do_not_share_one_engine_session(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "first job")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Doanh thu hôm nay là bao nhiêu"}})
            await h.until(lambda: len(h.asks) == 2, "second job")
            # Same engine key = same engine thread: the second job would queue behind the first
            # inside the engine, which is exactly the wait this change removes.
            self.assertNotEqual(h.keys[0], h.keys[1])
            self.assertTrue(h.keys[1], "the parallel job gets a key of its own")

        await self.run_route(script, ["a", "b"])

    async def test_acknowledgements_are_still_dropped_while_a_job_runs(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "first job")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Ok, xong thì báo anh nhé"}})
            await h.until(lambda: len(prov.acks) == 1, "acknowledgement closed")
            await asyncio.sleep(0.05)
            self.assertEqual(len(h.asks), 1, "a bare 'ok, tell me when done' is not a new job")

        await self.run_route(script, ["x"])

    async def test_without_a_status_voice_the_answer_goes_back_as_the_tool_reply(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "first job")
            await prov.q.put({"type": "tool_call", "id": "h2", "name": "ask_javis",
                              "args": {"request": "Xong chưa em"}})
            await h.until(lambda: len(prov.acks) == 1, "status returned as the tool reply")

        prov, *_ = await self.run_route(script, ["x"], status_supported=False)
        cid, text = prov.acks[0]
        self.assertEqual(cid, "h2")
        self.assertIn("Viết spec slide HTML", text, "providers that cannot speak a status answer through the tool reply")


class LiveRouteHeartbeatTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    FAST = dict(STATUS_FIRST_S=0.05, STATUS_EVERY_S=0.15, STATUS_TICK_S=0.01)

    async def _long_job(self, script_after, **kw):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "h1", "name": "ask_javis",
                              "args": {"request": "Viết spec slide HTML"}})
            await h.until(lambda: len(h.asks) == 1, "job running")
            await script_after(prov, h)

        return await self.run_route(script, ["Xong."], live_overrides=self.FAST, **kw)

    async def test_a_long_job_speaks_up_repeatedly(self):
        async def after(prov, h):
            await h.until(lambda: len(prov.status_calls) >= 2, "two unprompted status lines")

        prov, *_ = await self._long_job(after)
        self.assertTrue(all("Viết spec slide HTML" in t for t in prov.status_calls))

    async def test_it_stays_quiet_while_somebody_is_talking(self):
        async def after(prov, h):
            prov.quiet = False
            await asyncio.sleep(0.4)
            self.assertEqual(prov.status_calls, [], "never talk over the user or the model")
            prov.quiet = True
            await h.until(lambda: len(prov.status_calls) >= 1, "speaks once it is quiet again")

        await self._long_job(after)

    async def test_it_stops_when_the_job_ends(self):
        async def after(prov, h):
            await h.until(lambda: len(prov.status_calls) >= 1, "first status line")
            h.release(0)
            await h.until(lambda: len(prov.results) == 1, "job result")
            seen = len(prov.status_calls)
            await asyncio.sleep(0.4)
            self.assertEqual(len(prov.status_calls), seen, "no status line for a job that is over")

        await self._long_job(after)

    async def test_providers_that_cannot_speak_a_status_get_nothing_unprompted(self):
        async def after(prov, h):
            await asyncio.sleep(0.4)
            self.assertEqual(prov.acks, [], "no unprompted tool replies")

        await self._long_job(after, status_supported=False)

    async def test_the_model_reading_a_status_line_is_not_a_bubble_or_history(self):
        async def after(prov, h):
            await h.until(lambda: len(prov.status_calls) == 1, "status line handed to the model")
            # The model now reads it aloud: that turn must stay out of the chat.
            await prov.q.put({"type": "transcript", "role": "assistant", "text": "Em vẫn đang viết spec.",
                              "final": False})
            await prov.q.put({"type": "turn_done"})
            await h.until(lambda: any(f["type"] == "turn_done" for f in h.frames), "turn closed")

        prov, frames, asks, saved = await self._long_job(after)
        said = [f["text"] for f in frames if f["type"] == "transcript" and f.get("role") == "assistant"]
        self.assertEqual(said, [], "the spoken status is not a chat bubble")
        self.assertFalse(any("vẫn đang viết spec" in m["content"] for m in saved), "and not in the history")


if __name__ == "__main__":
    unittest.main()
