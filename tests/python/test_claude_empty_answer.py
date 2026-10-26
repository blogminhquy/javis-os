"""A Claude Code chat turn that ends with no words gets one more ask (0.332.0).

    python tests/run.py claude_empty_answer      (no network, fake Claude engine over the real WebSocket)

Owner report 26/10/2026: a plain question in the dashboard chat ("Là do composio hay do YouTube vậy") came back as
"(không có nội dung trả về - thử lại hoặc đổi model)". Claude Code had ended the turn cleanly without writing any
text (no tool call, no error): the model sometimes stops after its thinking alone. Javis now asks once more in the
same thread; an error or a plan limit is never retried, and an answer that has words is never asked again.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-empty-answer-")

import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
CALLS = []
SCRIPT = {"turns": []}


class FakeClaude:
    """Same contract as ClaudeSDK.query: text / final / error events. Each query plays the next scripted turn."""

    def __init__(self, **kw):
        self.system_prompt, self.model, self.session_id, self.effort = kw.get("system_prompt"), None, None, None
        self.mcp_config = None

    def reset_session(self):
        self.session_id = None

    def __getattr__(self, name):        # every other knob main sets (fast mode, MCP, hub...) is a no-op here
        return None

    async def query(self, prompt):
        CALLS.append({"prompt": prompt if isinstance(prompt, str) else str(prompt), "resume": self.session_id})
        for ev in (SCRIPT["turns"].pop(0) if SCRIPT["turns"] else []):
            yield dict(ev)


main.claude_engine = lambda **kw: FakeClaude(**kw)
main._apply_mcp = lambda *a, **k: None


def turn(text):
    sid = store.create_session(brain="brain", channel="web")
    got = []
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1:7777", "origin": "http://127.0.0.1:7777"}) as ws:
        ws.send_text(json.dumps({"message": text, "brain": "brain", "session_id": sid}))
        t0 = time.time()
        while time.time() - t0 < 20:
            m = json.loads(ws.receive_text())
            got.append(m)
            if m.get("type") == "turn_done":
                break
    return [m for m in got if m.get("type") == "response"], got


def final(text, sid="cs-1"):
    return {"type": "final", "content": text, "session_id": sid, "tokens_in": 5, "tokens_out": 1, "cost_usd": 0}


# 1. Empty, then an answer.
CALLS.clear()
SCRIPT["turns"] = [[final("")], [{"type": "text", "content": "Do YouTube ạ."}, final("Do YouTube ạ.")]]
resp, _ = turn("Là do composio hay do YouTube vậy")
check("the turn reached the (fake) Claude engine", len(CALLS) >= 1, CALLS)
check("an empty Claude turn is asked once more", len(CALLS) == 2, CALLS)
check("in the same thread (resumed), with the nudge",
      len(CALLS) == 2 and CALLS[1]["resume"] == "cs-1" and CALLS[1]["prompt"] == main.EMPTY_ANSWER_NUDGE, CALLS[1:])
check("the owner gets the answer, not an empty bubble", resp and resp[-1].get("content") == "Do YouTube ạ.", resp)

# 2. A normal answer is never asked again.
CALLS.clear()
SCRIPT["turns"] = [[{"type": "text", "content": "Chào anh."}, final("Chào anh.")]]
resp, _ = turn("chào")
check("an answer with words: one call only", len(CALLS) == 1 and resp and resp[-1].get("content") == "Chào anh.", CALLS)

# 3. An error is shown, never retried.
CALLS.clear()
SCRIPT["turns"] = [[{"type": "error", "content": "Claude lỗi gì đó"}, final("")]]
resp, got = turn("hỏi")
check("an engine error: no second ask (the error is already on screen)", len(CALLS) == 1, CALLS)
check("and the error reached the chat", any(m.get("type") == "error" for m in got), got)

# 4. Still empty after the nudge: one retry only, never a loop.
CALLS.clear()
SCRIPT["turns"] = [[final("")], [final("")], [final("x")]]
resp, _ = turn("hỏi lần nữa")
check("still empty: exactly one retry, then the old empty bubble", len(CALLS) == 2 and resp and resp[-1].get("content") == "",
      CALLS)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())
if fails:
    print(f"\nFAIL - test_claude_empty_answer: {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("\nOK - test_claude_empty_answer: all pass")
