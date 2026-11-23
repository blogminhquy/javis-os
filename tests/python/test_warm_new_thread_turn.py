"""A Claude chat turn that starts a new thread is served by the process opened ahead for it.

Measured 2026-11-23: 38% of Claude turns were cold because Javis had just rotated a long thread, and a turn without a
session never looked in the warm pool at all. This drives the real `claude_warm._query` over a fake `claude` client:

  - the first turn of a chat is cold and says it had no thread ("new_thread");
  - the next turn resumes on the kept process (warm);
  - `prepare_new_thread` closes that process and opens one on a new thread, one process at a time;
  - the rotated turn (no session) is served warm and learns its new session id, also when its system prompt differs
    from the previous turn's (on real history it did on 70% of rotated turns): the rule of every warm turn;
  - a rotated turn whose context rides in the system prompt (a prompt that is not plain text) does NOT use it, and
    the event names the part that changed.

Run:
    python tests/run.py warm_new_thread_turn
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-warm-turn-")
os.environ["JAVIS_WARM_BUDGET_MB"] = "400"       # room for ONE Claude process

import claude_warm  # noqa: E402
import warm_pool  # noqa: E402
from claude_cli import claude_engine  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  -> {detail!r}"))
    if not cond:
        fails.append(name)


eng = claude_engine(system_prompt="rules v1", cwd=tempfile.mkdtemp(), tag="chat:abc:1")
if type(eng).__name__ != "ClaudeSDK":
    print("skip: claude-agent-sdk not installed")
    raise SystemExit(0)

from claude_agent_sdk import ResultMessage  # noqa: E402

LOG = []          # what happened to the fake processes, in order
SESSIONS = iter(f"S{n}" for n in range(1, 50))


class FakeClient:
    def __init__(self, options):
        self.name = f"p{len([e for e in LOG if e.startswith('open')]) + 1}"
        self.resume = getattr(options, "resume", None)
        self.session = self.resume or None
        self.open = True

    async def query(self, prompt):
        if not self.open:
            raise RuntimeError("closed")

    async def receive_response(self):
        if self.session is None:
            self.session = next(SESSIONS)     # a process started without --resume opens a thread on its first turn
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id=self.session, result="ok")

    async def disconnect(self):
        self.open = False
        LOG.append("close " + self.name)

    async def interrupt(self):
        pass


async def fake_open(opts, handle):
    client = FakeClient(opts)
    LOG.append(f"open {client.name} resume={client.resume or '-'}")
    handle.client = client
    return handle


claude_warm._open = fake_open


async def turn(prompt="hi"):
    events = [ev async for ev in claude_warm._query(eng, prompt, "conv-1", allow_warm=True)]
    return next(ev for ev in events if ev["type"] == "warm"), events


async def main():
    warm, events = await turn()
    check("turn 1 (new chat) is cold and says it had no thread", warm == {"type": "warm", "warm": False,
                                                                          "cold": "new_thread"}, warm)
    check("turn 1 learned its session", eng.session_id == "S1", eng.session_id)
    check("turn 1 answered", any(ev["type"] == "final" for ev in events), [ev["type"] for ev in events])

    warm, _ = await turn()
    check("turn 2 resumes on the kept process", warm == {"type": "warm", "warm": True}, warm)
    check("still one process", LOG == ["open p1 resume=-"], LOG)

    check("the next turn will rotate: the new thread's process is asked for",
          await claude_warm.prepare_new_thread("conv-1"))
    await asyncio.sleep(0.05)
    check("the old process closed BEFORE the new one opened, and the new one resumes nothing",
          LOG == ["open p1 resume=-", "close p1", "open p2 resume=-"], LOG)
    check("one slot, same RAM", warm_pool.POOL.status()["used_mb"] == 300, warm_pool.POOL.status())

    eng.session_id = None                      # what main does when it rotates the thread
    warm, events = await turn()
    check("the rotated turn is served warm, and says a process was opened ahead for it",
          warm == {"type": "warm", "warm": True, "opened_ahead": True}, warm)
    check("no third process was started for it", len([e for e in LOG if e.startswith("open")]) == 2, LOG)
    check("the rotated turn learned the NEW session", eng.session_id == "S2", eng.session_id)

    warm, _ = await turn()
    check("the turn after resumes the new thread on the same process", warm["warm"] is True
          and len([e for e in LOG if e.startswith("open")]) == 2, (warm, LOG))

    # Another system prompt on the rotated turn: still served, the rule of every warm turn.
    await claude_warm.prepare_new_thread("conv-1")
    await asyncio.sleep(0.05)
    eng.session_id = None
    eng.system_prompt = "rules v2"
    warm, _ = await turn()
    check("another system prompt on the rotated turn: still served by the process opened ahead",
          warm.get("warm") is True and warm.get("opened_ahead") is True, warm)

    # A prompt that is not plain text: the turn's context rides in the system prompt, so it needs its own process.
    await claude_warm.prepare_new_thread("conv-1")
    await asyncio.sleep(0.05)
    eng.session_id = None
    opened = len([e for e in LOG if e.startswith("open")])
    warm, _ = await turn([{"type": "text", "text": "hi"}])
    check("a prompt that is not plain text: the process opened ahead is not used, and the event says which part",
          warm.get("warm") is False and warm.get("cold") == "config_changed"
          and warm.get("cold_parts") == ["new_thread_prompt"], warm)
    check("that turn ran on a process of its own", len([e for e in LOG if e.startswith("open")]) == opened + 1, LOG)

    # A forecast that turned out wrong (the next turn resumes after all) only costs one cold start.
    await claude_warm.prepare_new_thread("conv-1")
    await asyncio.sleep(0.05)
    warm, _ = await turn()
    check("a wrong forecast: the resumed turn runs cold and says the process was opened for a new thread",
          warm.get("warm") is False and warm.get("cold") == "config_changed" and "resume" in warm.get("cold_parts", []),
          warm)

    # The warm process refuses the message: the turn reruns cold and says so.
    held = warm_pool.POOL.peek("conv-1")
    held.handle.client.open = False
    try:
        await turn()
        check("a refused message raises for the cold rerun", False)
    except claude_warm._WarmStartFailed:
        events = [ev async for ev in claude_warm._query(eng, "hi", "conv-1", allow_warm=False)]
        warm = next(ev for ev in events if ev["type"] == "warm")
        check("the cold rerun says the warm start failed", warm.get("cold") == "warm_start_failed", warm)
    await warm_pool.POOL.close_all()


asyncio.run(main())

# An engine that never uses a warm process says why, before anything else.
eng.tag = "loop:x"


async def ineligible():
    async def nothing(cli, prompt):
        return
        yield
    claude_warm.cold_query = nothing
    return [ev async for ev in claude_warm.query(eng, "hi", "conv-2")]


first = asyncio.run(ineligible())
check("background work is told apart from a pool miss",
      first[:1] == [{"type": "warm", "warm": False, "cold": "not_owner_chat"}], first)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
