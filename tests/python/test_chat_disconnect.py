from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

import main
from chat_runtime import ChatRuntime
from sessions import SessionStore


class _DisconnectingWebSocket:
    cookies = {}

    def __init__(self, payload):
        self._payload = json.dumps(payload)
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def receive_text(self):
        if self._payload is not None:
            value, self._payload = self._payload, None
            return value
        raise WebSocketDisconnect()


def test_websocket_disconnect_does_not_cancel_turn(monkeypatch, tmp_path):
    async def scenario():
        runtime = ChatRuntime()
        store = SessionStore(tmp_path / "conversations.db")
        ws = _DisconnectingWebSocket({
            "message": "lam tiep khi dong tab",
            "brain": "brain",
            "session_id": "session-background",
        })

        monkeypatch.setattr(main, "_CHAT_RUNTIME", runtime)
        monkeypatch.setattr(main, "get_store", lambda: store)
        monkeypatch.setattr(main.cfgmod, "gate_active", lambda: False)
        monkeypatch.setattr(main.cfgmod, "read_settings", lambda: {"model": {}})
        monkeypatch.setattr(
            main, "_chat_provider",
            lambda _cfg: ("openrouter", "api", "test-key", "test-model"),
        )
        monkeypatch.setattr(main, "_reasoning_level", lambda _cfg: "off")
        # `**_kw` bắt buộc: build_system_prompt nay nhận thêm `lang` (khối NGÔN NGỮ).
        # Stub một tham số làm lời gọi thật ném TypeError, và lượt chat chết câm giữa
        # chừng - test đo nhầm sang nhánh lỗi thay vì nhánh đang muốn kiểm.
        monkeypatch.setattr(main, "build_system_prompt", lambda _brain, **_kw: "system")
        monkeypatch.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
        monkeypatch.setattr(
            main, "claude_engine",
            lambda **_kwargs: SimpleNamespace(session_id=None),
        )
        monkeypatch.setattr(main, "log_conversation", lambda *a, **k: None)
        monkeypatch.setattr(main.usage_store, "record", lambda *a, **k: None)

        async def no_schedule(*_args, **_kwargs):
            return None

        async def no_compact(*_args, **_kwargs):
            return False

        async def no_learn(*_args, **_kwargs):
            return None

        async def fake_stream(*_args, **_kwargs):
            async def events():
                await asyncio.sleep(0.03)
                yield {"type": "text", "content": "ket qua nen"}

            return events()

        monkeypatch.setattr(main, "_schedule_cancel_action", no_schedule)
        monkeypatch.setattr(main, "_api_stream_mcp", fake_stream)
        monkeypatch.setattr(main.compaction, "maybe_compact", no_compact)
        monkeypatch.setattr(main.learn_feature, "enqueue", no_learn)

        await main.websocket_endpoint(ws)

        # Socket đã đóng nhưng job vẫn thuộc runtime của server.
        assert runtime.get_job("session-background") is not None
        await asyncio.sleep(0.08)

        messages = store.get_messages("session-background")
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[-1]["content"] == "ket qua nen"
        assert runtime.get_job("session-background") is None

    asyncio.run(scenario())


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa từng
    # chạy một assertion nào. Bảy file từng ở tình trạng đó, và bốn assertion trong số
    # chúng đang ĐỎ mà không ai biết (xem CHANGELOG 0.13.2).
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
