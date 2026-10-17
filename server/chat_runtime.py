"""Vòng đời chat web độc lập với vòng đời WebSocket.

Một lượt chat là job của server. WebSocket chỉ là subscriber để nhận sự kiện,
vì vậy đóng/F5 tab không được phép huỷ job đang chạy.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional


Writer = Callable[[dict], Awaitable[None]]

# Fan-out to open pages (0.194.0). Before, `publish` awaited EVERY page's send. A page whose socket died without closing
# (phone asleep, Wi-Fi gone, a tab the browser froze) blocks its send until TCP gives up, and with it the running turn
# and every other page. Now a send that takes longer than SEND_WAIT_S keeps going in the background, later events for
# that page wait in its own backlog (order kept), and a page stuck past STUCK_S or BACKLOG_MAX events is dropped: its
# socket is closed and the page reconnects and resyncs from `hello`.
SEND_WAIT_S = 2.0
STUCK_S = 20.0
BACKLOG_MAX = 500


@dataclass
class _Client:
    writer: Writer
    on_drop: Optional[Callable[[], None]] = None
    pending: Optional[asyncio.Future] = None
    since: float = 0.0
    backlog: deque = field(default_factory=deque)


@dataclass
class ChatJob:
    task: asyncio.Task
    tag: str
    text: str = ""
    runtime_task_id: str = ""
    runtime_step_id: str = ""


class ChatRuntime:
    """Registry in-memory cho job chat và các kết nối đang xem."""

    def __init__(self) -> None:
        self._clients: Dict[str, _Client] = {}
        self._jobs: Dict[str, ChatJob] = {}

    def add_client(self, client_id: str, writer: Writer, on_drop: Optional[Callable[[], None]] = None) -> None:
        """`on_drop()` closes the page's socket when the runtime gives up on it (stuck sends)."""
        self._clients[client_id] = _Client(writer, on_drop)

    def remove_client(self, client_id: str) -> None:
        c = self._clients.pop(client_id, None)
        if c is not None:
            c.backlog.clear()
            if c.pending is not None and not c.pending.done():
                c.pending.cancel()

    def _drop(self, client_id: str, c: _Client) -> None:
        if self._clients.get(client_id) is not c:
            return
        self.remove_client(client_id)
        if c.on_drop is not None:
            try:
                c.on_drop()
            except Exception:  # noqa: BLE001 - the page is gone either way
                pass

    def _send(self, client_id: str, c: _Client, event: dict) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        fut = asyncio.ensure_future(c.writer(event))
        c.pending, c.since = fut, loop.time()

        def _next(f: asyncio.Future, cid=client_id, cl=c) -> None:
            if not f.cancelled():
                f.exception()   # retrieved: a dead socket's error must not be logged as "never retrieved"
            if self._clients.get(cid) is not cl or cl.pending is not f:
                return
            cl.pending = None
            if cl.backlog:
                self._send(cid, cl, cl.backlog.popleft())
        fut.add_done_callback(_next)
        return fut

    def register_job(self, session_id: str, task: asyncio.Task, tag: str,
                     runtime_task_id: str = "", runtime_step_id: str = "") -> None:
        self._jobs[session_id] = ChatJob(
            task=task, tag=tag,
            runtime_task_id=runtime_task_id, runtime_step_id=runtime_step_id,
        )

    def get_job(self, session_id: str) -> Optional[ChatJob]:
        job = self._jobs.get(session_id)
        if job and job.task.done():
            self._jobs.pop(session_id, None)
            return None
        return job

    def finish_job(self, session_id: str, task: asyncio.Task) -> None:
        """Không để callback của job cũ xoá nhầm job mới cùng session."""
        job = self._jobs.get(session_id)
        if job and job.task is task:
            self._jobs.pop(session_id, None)

    def cancel_session(self, session_id: str) -> Optional[str]:
        job = self.get_job(session_id)
        if not job:
            return None
        if not job.task.done():
            job.task.cancel()
        return job.tag

    def cancel_matching(self, tag_prefix: str) -> list[str]:
        """Huỷ asyncio job theo prefix; trả tag để caller giết subprocess."""
        tags: list[str] = []
        for job in list(self._jobs.values()):
            if not job.tag.startswith(tag_prefix):
                continue
            tags.append(job.tag)
            if not job.task.done():
                job.task.cancel()
            # Giữ entry tới finally của job để client vẫn nhận turn_done.
        return tags

    def snapshot(self) -> list[dict]:
        out = []
        for session_id in list(self._jobs):
            job = self.get_job(session_id)
            if job:
                item = {"session_id": session_id, "text": job.text}
                if job.runtime_task_id:
                    item["task_id"] = job.runtime_task_id
                if job.runtime_step_id:
                    item["step_id"] = job.runtime_step_id
                out.append(item)
        return out

    async def publish(self, event: dict) -> None:
        """Cập nhật snapshot rồi fan-out; writer tự nuốt lỗi socket đã chết."""
        session_id = str(event.get("session_id") or "")
        job = self.get_job(session_id) if session_id else None
        if job:
            kind = event.get("type")
            if kind == "stream":
                job.text += str(event.get("content") or "")
            elif kind == "response":
                job.text = str(event.get("content") or job.text)

        if not self._clients:
            return
        now = asyncio.get_running_loop().time()
        sends = []
        for cid, c in list(self._clients.items()):
            if c.pending is not None or c.backlog:
                # This page is still busy with an earlier event (`pending` clears only once the next one is taken
                # from the backlog, so order holds): queue behind it, or give up on it.
                if (not c.pending.done() and now - c.since > STUCK_S) or len(c.backlog) >= BACKLOG_MAX:
                    self._drop(cid, c)
                else:
                    c.backlog.append(event)
                continue
            sends.append(self._send(cid, c, event))
        if sends:
            # Healthy pages finish well inside the wait, so a caller still sees its event delivered when this returns.
            await asyncio.wait(sends, timeout=SEND_WAIT_S)
