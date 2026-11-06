"""A typed message is confirmed by the server, and a resend after a dead socket never runs twice.

    python tests/run.py chat_ack_resend      (no network)

Owner, 06/11/2026: on the phone, type, Enter, it spins, swipe to another app, and on return the whole exchange is gone,
not even in History; only sometimes. The phone had let the socket die while the page still saw it OPEN, so the message
went nowhere and the resync redrew the chat without it.

Pinned here:
  1. The server answers `chat_ack` once it has stored a message that carries `client_msg_id`.
  2. The same `client_msg_id` again (the page resends on the next socket) is acked as `dup` and starts no second turn.
  3. The page holds each typed message until its ack, resends it from `hello`, drops a socket that gave no ack, and
     keeps showing a held message when the chat is redrawn from the server.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import json
import time
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

import main
from chat_runtime import ChatRuntime
from sessions import SessionStore

APP = (DASHBOARD / "app.js").read_bytes().decode("utf-8")


class _ScriptedWebSocket:
    cookies = {}

    def __init__(self, payloads, gap=0.0):
        self._payloads = [json.dumps(p) for p in payloads]
        self._gap = gap
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def receive_text(self):
        if self._payloads:
            if self._gap:
                await asyncio.sleep(self._gap)
            return self._payloads.pop(0)
        raise WebSocketDisconnect()


def _stub_turn(monkeypatch, runtime, store, calls):
    monkeypatch.setattr(main, "_CHAT_RUNTIME", runtime)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main.cfgmod, "gate_active", lambda: False)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: {"model": {}})
    monkeypatch.setattr(main, "_chat_provider", lambda _cfg: ("openrouter", "api", "test-key", "test-model"))
    monkeypatch.setattr(main, "_reasoning_level", lambda _cfg: "off")
    monkeypatch.setattr(main, "build_system_prompt", lambda _brain, **_kw: "system")
    monkeypatch.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    monkeypatch.setattr(main, "claude_engine", lambda **_kwargs: SimpleNamespace(session_id=None))
    monkeypatch.setattr(main, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(main.usage_store, "record", lambda *a, **k: None)

    async def nothing(*_args, **_kwargs):
        return None

    async def no_compact(*_args, **_kwargs):
        return False

    async def fake_stream(*_args, **_kwargs):
        calls.append(1)

        async def events():
            await asyncio.sleep(0.02)
            yield {"type": "text", "content": "answer"}

        return events()

    monkeypatch.setattr(main, "_schedule_cancel_action", nothing)
    monkeypatch.setattr(main, "_api_stream_mcp", fake_stream)
    monkeypatch.setattr(main.compaction, "maybe_compact", no_compact)
    monkeypatch.setattr(main.learn_feature, "enqueue", nothing)


async def _wait(cond, limit_s=10.0):
    end = time.monotonic() + limit_s
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


def _acks(ws):
    return [f for f in ws.sent if f.get("type") == "chat_ack"]


def test_resend_is_acked_once_and_runs_once(monkeypatch, tmp_path):
    async def scenario():
        runtime = ChatRuntime()
        store = SessionStore(tmp_path / "conversations.db")
        calls = []
        _stub_turn(monkeypatch, runtime, store, calls)
        msg = {"message": "hello there", "brain": "brain", "session_id": "s-ack", "client_msg_id": "c1"}

        first = _ScriptedWebSocket([msg])
        await main.websocket_endpoint(first)
        acks = _acks(first)
        assert acks and acks[0]["client_msg_id"] == "c1" and acks[0]["dup"] is False, first.sent
        assert await _wait(lambda: runtime.get_job("s-ack") is None
                           and len(store.get_messages("s-ack")) >= 2), "turn did not finish"

        # The page did not see that ack (socket died) and sends the same message on its next socket.
        second = _ScriptedWebSocket([msg])
        await main.websocket_endpoint(second)
        acks = _acks(second)
        assert acks and acks[0]["dup"] is True and acks[0]["running"] is False, second.sent
        await asyncio.sleep(0.05)
        roles = [m["role"] for m in store.get_messages("s-ack")]
        assert roles == ["user", "assistant"], roles
        assert len(calls) == 1, "the resend ran the turn a second time"

    asyncio.run(scenario())


def test_resend_while_running_is_dup_and_running(monkeypatch, tmp_path):
    async def scenario():
        runtime = ChatRuntime()
        store = SessionStore(tmp_path / "conversations.db")
        calls = []
        _stub_turn(monkeypatch, runtime, store, calls)
        msg = {"message": "long job", "brain": "brain", "session_id": "s-run", "client_msg_id": "c2"}
        ws = _ScriptedWebSocket([msg, msg])
        await main.websocket_endpoint(ws)
        acks = _acks(ws)
        assert [a["dup"] for a in acks] == [False, True], ws.sent
        assert acks[1]["running"] is True
        assert not [f for f in ws.sent if f.get("type") == "error"], "a resend must not get the busy error"
        assert await _wait(lambda: runtime.get_job("s-run") is None)
        assert [m["role"] for m in store.get_messages("s-run")] == ["user", "assistant"]
        assert len(calls) == 1

    asyncio.run(scenario())


def test_message_without_id_is_unchanged(monkeypatch, tmp_path):
    async def scenario():
        runtime = ChatRuntime()
        store = SessionStore(tmp_path / "conversations.db")
        calls = []
        _stub_turn(monkeypatch, runtime, store, calls)
        ws = _ScriptedWebSocket([{"message": "no id", "brain": "brain", "session_id": "s-old"}])
        await main.websocket_endpoint(ws)
        assert not _acks(ws)
        assert await _wait(lambda: runtime.get_job("s-old") is None
                           and len(store.get_messages("s-old")) >= 2)

    asyncio.run(scenario())


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_page_holds_and_resends_until_ack():
    send = _fn("sendMessage")
    assert "payload.client_msg_id = newSid();" in send and "_trackUnacked(" in send
    assert "_sendUnacked(_held)" in send and "_dropUnacked(_held.id)" in send
    assert "_dropDeadSocket()" in _fn("_sendUnacked") and "ACK_WAIT_MS" in _fn("_sendUnacked")
    i = APP.index('if (data.type === "hello") {')
    hello = APP[i:APP.index("guiTinDutMang();", i)]
    assert hello.index("(data.running || []).forEach") < hello.index("_resendUnacked();") < hello.index("hideActivity()")
    assert 'if (data.type === "chat_ack") { _onChatAck(data); return; }' in APP
    ack = _fn("_onChatAck")
    assert "_dropUnacked(d.client_msg_id)" in ack and "openStoredSession(sid)" in ack
    assert "_drawUnacked(id, ds);" in _fn("_veLaiPhien")
    assert "_unackedOverdue()" in _fn("_resumeSauNgu")
    assert "_unacked.filter(u => u.sid !== sid)" in _fn("stopCurrent")
    assert "localStorage.setItem(UNACKED_KEY" in _fn("_saveUnacked")


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("skipped: pytest is not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
