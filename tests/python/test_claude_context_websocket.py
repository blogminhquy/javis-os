"""A tool-heavy Claude turn keeps the native thread on the next dashboard turn."""
from _paths import SERVER  # noqa: F401
import json
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-context-websocket-")

import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

main.cfgmod.gate_active = lambda: False
main._apply_mcp = lambda *args, **kwargs: None
resumed = []


class FakeClaude:
    def __init__(self, **kwargs):
        self.system_prompt = kwargs.get("system_prompt")
        self.model = self.session_id = self.effort = self.mcp_config = None

    def __getattr__(self, name):
        return None

    async def query(self, prompt):
        resumed.append(self.session_id)
        yield {"type": "request_context", "input_tokens": 160000}
        yield {"type": "text", "content": "Hello"}
        yield {"type": "final", "content": "Hello", "session_id": "claude-test-thread",
               "tokens_in": 1200000, "tokens_out": 3, "cost_usd": 0}


main.claude_engine = lambda **kwargs: FakeClaude(**kwargs)
store = main.get_store()
sid = store.create_session(brain="brain", channel="web")
client = TestClient(main.app, base_url="http://127.0.0.1")
headers = {"host": "127.0.0.1:7777", "origin": "http://127.0.0.1:7777"}

for message in ("First question", "Second question"):
    with client.websocket_connect("/ws", headers=headers) as ws:
        ws.send_text(json.dumps({"message": message, "brain": "brain", "session_id": sid}))
        while True:
            event = json.loads(ws.receive_text())
            if event.get("type") == "turn_done":
                break
    row = store.get_session(sid)
    assert row["last_input_tokens"] == 1200000
    assert row["last_context_input_tokens"] == 160000
    assert row["last_context_provider"] == "claude-code"

assert resumed == [None, "claude-test-thread"], resumed
print("PASS: tool-heavy turns keep their Claude thread")
