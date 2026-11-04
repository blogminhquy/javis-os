"""A Claude Code turn waits for its background work and reads the follow-up (0.453.0, issue #898 item 1).

    python tests/run.py claude_cho_viec_nen_0453 -v

Reported from a Windows Server install: when a Claude Code turn started background work (a background shell, a
sub-agent), the chat turn ended at the first answer and the follow-up that should pick up the result never came. Javis
disconnected at the first ResultMessage. The wait (claude_bg_wait.py) is wired into the owner's chat lane,
claude_warm.query, which every dashboard chat turn takes; this test drives that lane. The fake client shares ONE message
stream across receive_response() calls, like the SDK: a later call reads the messages after the first ResultMessage.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-bgwait-"))
import claude_agent_sdk as sdk
import claude_bg_wait as eng
import claude_warm
from claude_sdk_engine import ClaudeSDK

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def answer(text):
    return sdk.AssistantMessage(content=[sdk.TextBlock(text=text)], model="sonnet", stop_reason="end_turn")


def result(text, cost=0.01):
    return sdk.ResultMessage(subtype="success", duration_ms=100, duration_api_ms=90, is_error=False, num_turns=1,
                             session_id="s1", result=text, total_cost_usd=cost,
                             usage={"input_tokens": 7, "output_tokens": 3})


def task(tid, status=None):
    if status is None:
        return sdk.SystemMessage(subtype="task_started", data={"task_id": tid})
    return sdk.SystemMessage(subtype="task_notification", data={"task_id": tid, "status": status})


class Client:
    """One stream for the whole connection. `script` runs as a task feeding the queue; `on_query` reacts to a query."""

    def __init__(self, script, on_query=None):
        self.q = asyncio.Queue()
        self.script, self.on_query = script, on_query
        self.queries = []
        self.closed = False

    async def connect(self):
        pass

    async def query(self, prompt):
        self.queries.append(prompt)
        if len(self.queries) == 1:
            asyncio.get_running_loop().create_task(self.script(self.q))
        elif self.on_query:
            asyncio.get_running_loop().create_task(self.on_query(self.q, prompt))

    async def interrupt(self):
        pass

    async def disconnect(self):
        self.closed = True

    async def receive_response(self):
        while True:
            m = await self.q.get()
            yield m
            if isinstance(m, sdk.ResultMessage):
                return


async def run_case(client, env=None, limit=3.0):
    e = {"JAVIS_CLAUDE_RESULT_TIMEOUT": "30", "JAVIS_CLAUDE_IDLE_TIMEOUT": "0", "JAVIS_CLAUDE_FIRST_TIMEOUT": "0",
         "JAVIS_WARM_BUDGET_MB": "0.0001"}
    e.update(env or {})
    with patch.object(sdk, "ClaudeSDKClient", return_value=client), \
         patch.object(ClaudeSDK, "is_available", return_value=True), \
         patch.object(ClaudeSDK, "_options", return_value=SimpleNamespace(include_hook_events=True)), \
         patch("claude_token_gate.xep_hang", return_value=""), \
         patch.dict(os.environ, e):
        engine = ClaudeSDK(tag="chat:bgwait-test")
        assert claude_warm.eligible(engine), "the test must run the owner's chat lane"
        events = []

        async def consume():
            async for ev in claude_warm.query(engine, "render video", "bgwait-key"):
                events.append(ev)
        await asyncio.wait_for(consume(), limit)
    return events


def finals(evs):
    return [e for e in evs if e["type"] == "final"]


def streamed(evs):
    return "".join(e["content"] for e in evs if e["type"] == "text")


async def main():
    # 1. Claude Code carries on by itself once its background task is done.
    async def auto(q):
        await q.put(task("bg1"))
        await q.put(answer("Đang render nền."))
        await q.put(result("Đang render nền."))
        await asyncio.sleep(0.1)
        await q.put(task("bg1", "completed"))
        await q.put(answer("Render xong, video ở out.mp4."))
        await q.put(result("Render xong, video ở out.mp4.", cost=0.02))
    c = Client(auto)
    evs = await run_case(c)
    f = finals(evs)
    check("the turn stays open past the first answer while a background task runs", len(f) == 2, f)
    check("the last final carries both answers (the chat saves the last final)",
          f and "Đang render nền." in f[-1]["content"] and "out.mp4" in f[-1]["content"], f[-1] if f else None)
    check("the follow-up starts a new paragraph in the streamed text", "\n\n" in streamed(evs), streamed(evs))
    check("Claude Code carried on by itself: Javis did not nudge", c.queries == ["render video"], c.queries)
    check("the connection closes once the work is done", c.closed)

    # 2. Tasks done and Claude Code silent: Javis nudges it once.
    async def silent(q):
        await q.put(task("bg1"))
        await q.put(answer("Đang chạy test nền."))
        await q.put(result("Đang chạy test nền."))
        await asyncio.sleep(0.05)
        await q.put(task("bg1", "completed"))

    async def on_nudge(q, prompt):
        await q.put(answer("Test xanh hết."))
        await q.put(result("Test xanh hết."))
    c = Client(silent, on_nudge)
    with patch.object(eng, "BG_NUDGE_S", 0.1):
        evs = await run_case(c)
    check("silent after the tasks finish: Javis asks Claude Code to carry on, once",
          len(c.queries) == 2 and c.queries[1] == eng.BG_NUDGE, c.queries)
    check("and the answer to the nudge is the turn's last final", finals(evs) and "Test xanh" in finals(evs)[-1]["content"])

    # 3. No background task: the turn ends at the first result, as before.
    async def plain(q):
        await q.put(answer("Chào anh."))
        await q.put(result("Chào anh."))
    c = Client(plain)
    evs = await run_case(c)
    check("no background task: one final, no wait, no nudge", len(finals(evs)) == 1 and c.queries == ["render video"])

    # 4. The wait has a cap: still running at the cap, Javis says so and stops waiting.
    async def endless(q):
        await q.put(task("bg1"))
        await q.put(answer("Đang build."))
        await q.put(result("Đang build."))
    c = Client(endless)
    evs = await run_case(c, env={"JAVIS_CLAUDE_BG_WAIT": "0.3"})
    check("past JAVIS_CLAUDE_BG_WAIT the turn ends and says why",
          len(finals(evs)) == 1 and "JAVIS_CLAUDE_BG_WAIT" in streamed(evs) and c.closed, streamed(evs))

    # 5. JAVIS_CLAUDE_BG_WAIT=0 brings back the old behaviour.
    c = Client(endless)
    evs = await run_case(c, env={"JAVIS_CLAUDE_BG_WAIT": "0"})
    check("JAVIS_CLAUDE_BG_WAIT=0: the turn ends at the first result", len(finals(evs)) == 1
          and "JAVIS_CLAUDE_BG_WAIT" not in streamed(evs))

    # 6. A failed result never waits.
    async def failed(q):
        await q.put(task("bg1"))
        await q.put(sdk.ResultMessage(subtype="error_during_execution", duration_ms=1, duration_api_ms=1, is_error=True,
                                      num_turns=1, session_id="s1", result="boom"))
    c = Client(failed)
    evs = await run_case(c)
    check("an error result ends the turn even with a task pending", len(finals(evs)) <= 1 and c.closed)

    # 7. The rounds are capped (a follow-up that keeps starting new background work).
    w = eng.BackgroundWait(100.0, max_rounds=2)
    comp = SimpleNamespace(tasks={"t"}, deadline=None)
    ok = [w.keep_going(SimpleNamespace(is_error=False), comp, 0.0) for _ in range(3)]
    check("at most BG_MAX_ROUNDS waits per turn", ok == [True, True, False], ok)


asyncio.run(main())

import hashlib  # noqa: E402
import json  # noqa: E402
pin = json.loads((ROOT / "docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json").read_text())
check("claude_sdk_engine.py stays byte for byte the qualified source (the wait lives in claude_bg_wait.py)",
      hashlib.sha256((ROOT / "server/claude_sdk_engine.py").read_bytes()).hexdigest()
      == pin["source_hashes"]["claude_sdk_engine.py"])
check("claude_bg_wait.py is not part of the qualified native profile", "claude_bg_wait.py" not in pin["source_hashes"])

print("\n" + ("XANH" if not fails else f"ĐỎ: {len(fails)} lỗi"))
raise SystemExit(1 if fails else 0)
