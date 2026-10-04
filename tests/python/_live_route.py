"""Shared harness for the /ws/voice-live route tests. No network, no real Codex.

The route is a closure-heavy async function inside server/main.py, so the tests compile just that
function out of the module and run it in a namespace of fakes: a provider that records what the
route says to it, a brain (`_voice_ask_javis`) the test releases by hand, a browser socket, and a
real SessionStore in a temp directory.

    class MyTests(LiveRouteMixin, unittest.IsolatedAsyncioTestCase):
        async def test_x(self):
            async def script(prov, h): ...
            prov, frames, asks, saved = await self.run_route(script, ["answer for ask 0"])

`script(prov, h)` drives the call. `h` carries:
  until(cond, what)   wait for a condition or fail the test
  release(n)          let the n-th brain call return its answer
  asks, keys          request text and engine key of each brain call, in call order
  progress            n -> the `progress` callback the route gave the n-th brain call
  frames, inbox       frames sent to the browser / frames the browser sends up
"""
from _paths import ROOT, SERVER  # noqa: F401
import ast
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

import sessions
import voice_live

# What the route reads from the `voice_live` module. Missing names stay None so a route that has
# not been changed yet fails on behaviour, not on a harness AttributeError.
_ROUTE_NAMES = ("is_followup_ack", "is_same_request", "is_noop_result", "FOLLOWUP_ACK",
                "parallel_request", "is_progress_question", "status_line",
                "STATUS_FIRST_S", "STATUS_EVERY_S", "STATUS_TICK_S")


def route_tree():
    tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
    route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "voice_live_ws")
    route.decorator_list = []
    return ast.Module(body=[route], type_ignores=[])


class FakeProvider:
    """A ChatGPT-Live-shaped provider. `status_supported=False` makes it behave like the others
    (Gemini, OpenAI Realtime), which cannot speak a status line on their own."""
    name = "chatgpt"
    model = ""
    transport = "webrtc"
    wants_reconnect = False

    def __init__(self, status_supported=True):
        self.q = asyncio.Queue()
        self.results, self.acks, self.status_calls = [], [], []
        self.status_supported = status_supported
        self.quiet = True

    async def connect(self): pass
    async def restore_history(self, history): pass
    def supports_async_tools(self): return True
    async def close(self): pass
    async def send_tool_running(self, cid, name): pass
    async def send_context(self, text): pass
    async def send_text(self, text): pass

    async def send_tool_result(self, cid, name, result):
        self.results.append((cid, result))

    async def send_tool_ack(self, cid, name, text):
        self.acks.append((cid, text))

    async def say_status(self, text):
        if self.status_supported:
            self.status_calls.append(text)
        return self.status_supported

    def is_quiet(self):
        return self.quiet

    async def events(self):
        while True:
            ev = await self.q.get()
            if ev is None:
                return
            yield ev


class LiveRouteMixin:
    async def run_route(self, script, answers, status_supported=True, live_overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            store = sessions.SessionStore(str(Path(directory) / "sessions.db"))
            try:
                return await self._run_in(store, directory, script, answers, status_supported, live_overrides or {})
            finally:
                store._conn.close()

    async def _run_in(self, store, directory, script, answers, status_supported, live_overrides):
        sid = store.get_or_create(None, brain="brain", engine="test", model="test")
        frames, asks, keys, progress = [], [], [], {}
        inbox = asyncio.Queue()
        prov = FakeProvider(status_supported)

        class Socket:
            async def accept(self): pass

            async def send_text(self, text):
                frames.append(json.loads(text))

            async def receive(self):
                return {"text": json.dumps(await inbox.get())}

            async def close(self): pass

        gates = {}

        async def ask(req, conv_sid, brain, key="", progress=None):
            n = len(asks)
            asks.append(req)
            keys.append(key)
            progress_cbs[n] = progress
            gate = gates.setdefault(n, asyncio.Event())
            await gate.wait()
            return answers[n]

        progress_cbs = progress
        names = {n: getattr(voice_live, n, None) for n in _ROUTE_NAMES}
        names.update(live_overrides)
        namespace = dict(
            asyncio=asyncio, json=json, sys=sys, WebSocket=Socket, Query=lambda x: x,
            cfgmod=types.SimpleNamespace(gate_active=lambda: False,
                                         read_settings=lambda: {"voice": {"live_provider": "chatgpt"}}),
            voice_live=types.SimpleNamespace(
                make_provider=lambda cfg, recognition_lang="vi-VN", memory_index="": prov, MEMORY_CHARS=4000, **names),
            openai_oauth=types.SimpleNamespace(write_codex_auth=lambda: None),
            _brain_memory_dir=lambda root: Path(directory), _brain_root=lambda b: directory,
            _fit_memory_index=lambda mem, cap=None: mem[:cap],
            _voice_ask_javis=ask, get_store=lambda: store, _brain_key=lambda b: b,
            voice_call=types.SimpleNamespace(live_settings=lambda c: c))
        exec(compile(route_tree(), "live-route", "exec"), namespace)
        route = asyncio.ensure_future(namespace["voice_live_ws"](Socket(), sid, "brain", "vi-VN"))

        async def until(cond, what, tries=300):
            for _ in range(tries):
                if cond():
                    return
                await asyncio.sleep(0.01)
            self.fail("waited too long for: " + what)

        def release(n):
            gates.setdefault(n, asyncio.Event()).set()

        try:
            await script(prov, types.SimpleNamespace(until=until, release=release, asks=asks, keys=keys,
                                                     progress=progress, frames=frames, inbox=inbox))
        finally:
            await inbox.put({"type": "stop"})
            await prov.q.put(None)
            for gate in gates.values():
                gate.set()
            await asyncio.wait_for(route, 5)
        return prov, frames, asks, [m for m in store.get_messages(sid)]
