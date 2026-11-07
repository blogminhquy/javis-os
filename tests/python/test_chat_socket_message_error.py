"""One message that fails on the server does not take the chat socket down.

    python tests/run.py chat_socket_message_error      (no network)

Users, 07/11/2026: "Mất kết nối tới máy chủ. Đang nối lại..." for a whole afternoon, a server restart did not help.
The receive loop of /ws only caught WebSocketDisconnect, so any error while taking a message ended the handler and
closed the socket. The page reconnected and its `hello` sent the unconfirmed message again (it keeps it in
localStorage until `chat_ack`), which failed the same way: the socket died every 3 seconds, forever.

Pinned here:
  1. A message that raises gets a rejected `chat_ack` (the page stops resending it), an error and `turn_done` for its
     chat, and the same socket goes on to take the next message.
  2. A frame that is not JSON is skipped instead of closing the socket.
  3. The page gives a message back to the input box after a few sockets that never acked it, so no server bug can
     make it resend forever.
  4. A socket refused at the handshake makes the page ask /auth/status: an expired login shows the sign-in screen
     instead of "Mất kết nối" forever.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import json

import main
from chat_runtime import ChatRuntime
from sessions import SessionStore

from test_chat_ack_resend import _ScriptedWebSocket, _stub_turn, _wait, _acks

APP = (DASHBOARD / "app.js").read_bytes().decode("utf-8")


def test_failing_message_keeps_the_socket(monkeypatch, tmp_path):
    async def scenario():
        runtime = ChatRuntime()
        store = SessionStore(tmp_path / "conversations.db")
        calls = []
        _stub_turn(monkeypatch, runtime, store, calls)
        real = store.get_or_create
        state = {"failed": 0}

        def flaky(sid, *a, **k):
            if sid == "s-bad":
                state["failed"] += 1
                raise OSError("disk went away")
            return real(sid, *a, **k)

        monkeypatch.setattr(store, "get_or_create", flaky)
        ws = _ScriptedWebSocket([
            {"placeholder": True},
            {"message": "boom", "brain": "brain", "session_id": "s-bad", "client_msg_id": "c-bad"},
            {"message": "fine", "brain": "brain", "session_id": "s-ok", "client_msg_id": "c-ok"},
        ])
        ws._payloads[0] = "not json"      # a raw frame that is not JSON
        await main.websocket_endpoint(ws)  # must end on the scripted disconnect, not raise
        assert state["failed"] == 1
        acks = {a["client_msg_id"]: a for a in _acks(ws)}
        assert acks["c-bad"].get("rejected") is True and acks["c-bad"]["dup"] is False, ws.sent
        assert acks["c-ok"]["dup"] is False and not acks["c-ok"].get("rejected"), ws.sent
        bad = [f for f in ws.sent if f.get("session_id") == "s-bad"]
        assert [f["type"] for f in bad] == ["chat_ack", "error", "turn_done"], bad
        assert "OSError" in bad[1]["content"]
        assert await _wait(lambda: runtime.get_job("s-ok") is None
                           and len(store.get_messages("s-ok")) >= 2), "the next message did not run"
        assert len(calls) == 1

    asyncio.run(scenario())


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_page_stops_resending_after_a_few_sockets():
    assert "u.tries = (u.tries || 0) + 1;" in _fn("_sendUnacked")
    resend = _fn("_resendUnacked")
    assert "u.tries >= MAX_RESENDS" in resend
    assert 'window.t("app.ws_tin_loi")' in resend


def test_refused_handshake_checks_the_login():
    i = APP.index("ws.onclose = (e) => {")
    onclose = APP[i:APP.index("};", i)]
    assert "if (!_wsMoLuc) _checkLoginAfterRefusal();" in onclose
    check = _fn("_checkLoginAfterRefusal")
    assert "_fetchAuthStatus(1" in check and "s.auth_required && !s.authed" in check
    assert "initAuthGate()" in check


def test_new_text_is_in_both_languages():
    for lang in ("vi", "en"):
        d = json.loads((DASHBOARD / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert d.get("app.ws_tin_loi") and d.get("app.ws_login_lost"), lang


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("skipped: pytest is not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
