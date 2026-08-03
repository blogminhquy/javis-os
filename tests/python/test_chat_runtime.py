from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio

from chat_runtime import ChatRuntime


async def _collect(target, event):
    target.append(event)


def test_job_survives_client_disconnect_and_replays_snapshot():
    async def scenario():
        runtime = ChatRuntime()
        release = asyncio.Event()
        received = []

        async def work():
            await release.wait()

        task = asyncio.create_task(work())
        runtime.register_job("sid-1", task, "chat:turn-1")
        runtime.add_client("tab-1", lambda event: _collect(received, event))

        await runtime.publish(
            {"type": "stream", "session_id": "sid-1", "content": "dang chay"}
        )
        runtime.remove_client("tab-1")

        assert not task.cancelled()
        assert not task.done()
        assert runtime.snapshot() == [{"session_id": "sid-1", "text": "dang chay"}]

        reconnected = []
        runtime.add_client("tab-2", lambda event: _collect(reconnected, event))
        await runtime.publish(
            {"type": "stream", "session_id": "sid-1", "content": " tiep"}
        )
        assert reconnected[-1]["content"] == " tiep"
        assert runtime.snapshot() == [
            {"session_id": "sid-1", "text": "dang chay tiep"}
        ]

        release.set()
        await task
        runtime.finish_job("sid-1", task)
        assert runtime.snapshot() == []

    asyncio.run(scenario())


def test_stop_cancels_only_selected_session():
    async def scenario():
        runtime = ChatRuntime()
        hold = asyncio.Event()

        async def work():
            await hold.wait()

        first = asyncio.create_task(work())
        second = asyncio.create_task(work())
        runtime.register_job("sid-1", first, "chat:first")
        runtime.register_job("sid-2", second, "chat:second")

        assert runtime.cancel_session("sid-1") == "chat:first"
        await asyncio.sleep(0)
        assert first.cancelled()
        assert not second.done()

        second.cancel()
        await asyncio.gather(second, return_exceptions=True)

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
