"""Hanging up a Live call keeps the work the main brain is still doing (GitHub issue 1315, point 3). No network.

    python tests/run.py voice_live_hangup

A user asked Javis to keep checking, hung up, and the answer never arrived: when the socket closed, the route
cancelled every running handoff. Pins:
  - a handoff still running at hang-up is kept (joins the chat's voice background work) and finishes;
  - its answer is posted to the call's chat (`_voice_after_call`), never sent on the closed socket or to the closed
    provider, and a "nothing new" follow-up posts nothing;
  - a file pasted during the call and still being read is kept the same way;
  - the call's other tasks (the long-job heartbeat) still stop;
  - the voice background time limit stops a kept handoff and says so; stopping the background work says so too;
  - `_voice_after_call` posts through `_notify_owner` to `web:<sid>` with a job card, with no pronoun or long dash;
  - a new call in the same chat does not queue behind a handoff left running (`_voice_ask_javis` shared circuit).
"""
from _paths import ROOT, SERVER  # noqa: F401
import ast
import asyncio
import re
import sys
import types
import unittest
import uuid

import voice_live
from _live_route import LiveRouteMixin

FAST_HEARTBEAT = {"STATUS_FIRST_S": 0.0, "STATUS_EVERY_S": 0.0, "STATUS_TICK_S": 0.01}


def _session_id(frames):
    return next(f for f in frames if f["type"] == "ready")["session_id"]


class HangUpRouteTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
    async def _hang_up(self, h):
        await h.inbox.put({"type": "stop"})
        await asyncio.wait_for(asyncio.shield(h.route), 5)

    async def test_running_handoff_finishes_and_posts_to_the_chat(self):
        seen = {}

        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis",
                              "args": {"request": "kiểm tra doanh thu tuần này"}})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            await self._hang_up(h)
            seen["frames"] = len(h.frames)
            self.assertEqual(len(h.kept), 1, "the running handoff joins the chat's background work")
            self.assertEqual(h.after_call, [], "nothing posted before the brain answers")
            h.release(0)
            await h.until(lambda: h.after_call, "the answer is posted after the call")
            seen["after"] = list(h.after_call)
            seen["late"] = list(h.late_sends)

        prov, frames, _asks, saved = await self.run_route(script, ["Doanh thu tuần này 120 triệu."])
        sid = _session_id(frames)
        self.assertEqual(seen["after"], [(sid, "kiểm tra doanh thu tuần này", "Doanh thu tuần này 120 triệu.", "done")])
        self.assertEqual(len(frames), seen["frames"], "nothing more is sent on the closed socket")
        self.assertEqual(seen["late"], [])
        self.assertEqual(prov.results, [], "the closed provider gets no tool result")
        self.assertEqual(prov.after_close, [])
        self.assertFalse(any(f["type"] == "tool_result" for f in frames))
        self.assertFalse(any("120 triệu" in m["content"] for m in saved),
                         "the route does not store it itself: the chat delivery does, once")

    async def test_pasted_file_still_being_read_is_kept(self):
        async def script(prov, h):
            await h.inbox.put({"type": "ask", "text": "[File đính kèm]\n\nxem ảnh này", "display": "xem ảnh này",
                               "files": ["a.png"]})
            await h.until(lambda: len(h.asks) == 1, "the brain reads the file")
            await self._hang_up(h)
            h.release(0)
            await h.until(lambda: h.after_call, "the answer is posted after the call")

        prov, frames, _asks, _saved = await self.run_route(script, ["Ảnh là một bát mì."])
        self.assertEqual(self.posted_items(), [("xem ảnh này", "Ảnh là một bát mì.", "done")])
        self.assertEqual(prov.readbacks, [])
        self.assertEqual(prov.after_close, [])

    async def test_heartbeat_still_stops_at_hang_up(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis", "args": {"request": "báo cáo dài"}})
            await h.until(lambda: prov.status_calls, "the long-job heartbeat speaks during the call")
            await self._hang_up(h)
            await asyncio.sleep(0.1)   # several heartbeat ticks
            h.release(0)
            await h.until(lambda: h.after_call, "the answer is posted after the call")

        prov, _frames, _asks, _saved = await self.run_route(script, ["xong"], live_overrides=FAST_HEARTBEAT)
        self.assertEqual(prov.after_close, [], "the heartbeat does not talk to the closed provider")

    async def test_time_limit_stops_a_kept_handoff_and_says_so(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis", "args": {"request": "quét kho"}})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            await self._hang_up(h)
            await h.until(lambda: h.after_call, "the time limit posts a line")

        prov, frames, _asks, _saved = await self.run_route(script, ["never"], after_call_limit=0.05)
        self.assertEqual(self.posted_items(), [("quét kho", "", "timeout")])

    async def test_stopping_the_background_work_cancels_it_and_says_so(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis", "args": {"request": "quét kho"}})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            await self._hang_up(h)
            h.kept[0].cancel()   # what huy_viec_nen_giong does for "stop the background work"
            await h.until(lambda: h.after_call, "the stop is posted")

        prov, frames, _asks, _saved = await self.run_route(script, ["never"])
        self.assertEqual(self.posted_items(), [("quét kho", "", "cancelled")])

    async def test_nothing_new_follow_up_posts_nothing(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis", "args": {"request": "tra đơn hàng"}})
            await h.until(lambda: len(h.asks) == 1, "the first job runs")
            await prov.q.put({"type": "tool_call", "id": "c2", "name": "ask_javis",
                              "args": {"request": "nhớ kèm cả đơn hôm qua"}})
            await h.until(lambda: len(h.asks) == 2, "the follow-up runs in parallel")
            await self._hang_up(h)
            self.assertEqual(len(h.kept), 2)
            h.release(1)
            h.release(0)
            await h.until(lambda: h.after_call, "the real answer is posted")
            await asyncio.sleep(0.05)

        prov, frames, _asks, _saved = await self.run_route(script, ["3 đơn mới.", voice_live.FOLLOWUP_NOOP])
        self.assertEqual(self.posted_items(), [("tra đơn hàng", "3 đơn mới.", "done")])

    async def test_answer_given_during_the_call_is_not_posted_again(self):
        async def script(prov, h):
            await prov.q.put({"type": "tool_call", "id": "c1", "name": "ask_javis", "args": {"request": "tra đơn"}})
            await h.until(lambda: len(h.asks) == 1, "the brain runs")
            h.release(0)
            await h.until(lambda: prov.results, "the answer reaches the model during the call")
            await self._hang_up(h)
            self.assertEqual(h.kept, [])

        prov, frames, _asks, _saved = await self.run_route(script, ["3 đơn."])
        self.assertEqual(self.posted_items(), [])

    async def run_route(self, script, answers, **kw):
        """Also keeps what was posted after the call as `self.posted`: [(request, answer, status)]."""
        self.posted = []

        async def wrapped(prov, h):
            self.posted = h.after_call
            await script(prov, h)

        return await super().run_route(wrapped, answers, **kw)

    def posted_items(self):
        return [(req, res, st) for _sid, req, res, st in self.posted]


def _compile(name, **namespace):
    tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), name, "exec"), namespace)
    return namespace[name]


class AfterCallDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def _deliver(self, lang="vi"):
        sent = []

        async def notify(owner_chat, text, **kw):
            sent.append((owner_chat, text, kw))
            return True, ""

        fn = _compile("_voice_after_call", _notify_owner=notify, WEB_CHAT_PREFIX="web:", VOICE_BG_TIMEOUT=600.0,
                      sys=sys, localefmt=types.SimpleNamespace(chu=lambda vi, en: vi if lang == "vi" else en))
        return fn, sent

    async def test_answer_goes_to_the_calls_chat_with_a_job_card(self):
        fn, sent = self._deliver()
        self.assertTrue(await fn("S1", "brain", "kiểm tra doanh thu", "120 triệu."))
        owner, text, kw = sent[0]
        self.assertEqual(owner, "web:S1")
        self.assertEqual(text, "120 triệu.")
        self.assertEqual(kw["viec"], {"kind": "job", "status": "done", "title": "kiểm tra doanh thu"})
        self.assertEqual(kw["kind"], "answer")
        self.assertEqual(kw["brain"], "brain")

    async def test_empty_answer_or_chat_posts_nothing(self):
        fn, sent = self._deliver()
        self.assertFalse(await fn("S1", "brain", "x", "  "))
        self.assertFalse(await fn("", "brain", "x", "answer"))
        self.assertEqual(sent, [])

    async def test_stopped_work_says_so_without_pronouns_or_long_dashes(self):
        for lang in ("vi", "en"):
            fn, sent = self._deliver(lang)
            await fn("S1", "brain", "quét kho", "", status="timeout")
            await fn("S1", "brain", "quét kho", "", status="cancelled")
            self.assertEqual([kw["viec"]["status"] for _o, _t, kw in sent], ["timeout", "cancelled"])
            self.assertIn("10", sent[0][1], "the time limit is named in minutes")
            for _o, text, _kw in sent:
                self.assertTrue(text)
                self.assertNotIn("\u2014", text)
                self.assertNotIn("\u2013", text)
                if lang == "vi":
                    self.assertIsNone(re.search(r"\b(anh|em|mình|bạn|chị)\b", text.lower()), text)


class SharedCircuitTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_new_call_does_not_queue_behind_a_kept_handoff(self):
        keys, gates = [], {}

        async def tg_answer(request, meta=None, **kw):
            keys.append(meta["chat_id"])
            gate = gates.setdefault(request, asyncio.Event())
            await gate.wait()
            return {"text": request + " ok"}

        runs = {}
        ask = _compile("_voice_ask_javis", _VOICE_SHARED_RUNS=runs, uuid=uuid, os=__import__("os"), _TG_SESS={},
                       _voice_agent=lambda s, b: None, _tg_session=lambda k: {}, _agent_sess_key=lambda k, a: k,
                       _brain_root=lambda b: "/nonexistent-brain", _tg_answer=tg_answer,
                       channel_context=types.SimpleNamespace(strip_control_blocks=lambda t: t))
        left = asyncio.ensure_future(ask("old", "S1", "brain"))      # kept after the previous call ended
        await asyncio.sleep(0)
        self.assertEqual(keys, ["voice:S1"])
        self.assertEqual(runs, {"S1": 1})
        new = asyncio.ensure_future(ask("new", "S1", "brain"))       # the next call's first handoff
        await asyncio.sleep(0)
        self.assertRegex(keys[1], r"^voice:S1:[0-9a-f]{8}$", "a one-shot circuit, not a queue behind the old one")
        gates.setdefault("new", asyncio.Event()).set()
        self.assertEqual(await new, "new ok")
        gates.setdefault("old", asyncio.Event()).set()
        self.assertEqual(await left, "old ok")
        self.assertEqual(runs, {}, "the counter is cleared once the shared circuit is free")
        gates.setdefault("again", asyncio.Event()).set()
        await ask("again", "S1", "brain")
        self.assertEqual(keys[2], "voice:S1", "a free chat uses its shared circuit again")
        gates.setdefault("own", asyncio.Event()).set()
        await ask("own", "S1", "brain", key="voice:S1:p2")
        self.assertEqual(keys[3], "voice:S1:p2")
        self.assertEqual(runs, {}, "a run on its own circuit does not touch the counter")


if __name__ == "__main__":
    unittest.main()
