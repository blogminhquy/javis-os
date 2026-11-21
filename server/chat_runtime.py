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


def _xep_hang(backlog: deque, event: dict) -> None:
    """Queue `event` behind a busy page, folding a `stream` piece into the stream piece right before it (0.444.1).

    Since 0.438.4-0.438.6 every engine streams its answer a few characters per event. A page that falls behind (a phone,
    a slow laptop busy drawing) used to queue one event per piece, hit BACKLOG_MAX within seconds and get dropped, then
    reconnect and fall behind again (VPS users, 2026-11-03: "Reconnecting", a frozen machine). Two queued pieces of the
    same answer carry the same fields apart from `content`, so the page loses nothing when they travel as one event.
    The queued event is replaced by a copy, never edited: the same dict may sit in another page's backlog."""
    if event.get("type") == "stream" and backlog:
        last = backlog[-1]
        if (isinstance(last, dict) and last.get("type") == "stream"
                and {k: v for k, v in last.items() if k != "content"} == {k: v for k, v in event.items() if k != "content"}):
            backlog[-1] = {**last, "content": str(last.get("content") or "") + str(event.get("content") or "")}
            return
    backlog.append(event)


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

    # 16/11/2026: `on_finish(session_id)` is called once a registered job is over, however it ended (answer, error,
    # Stop, cancel). The host uses it to close the turn's row in turn_ledger.py. Never raises into the runtime.
    on_finish: Optional[Callable[[str], None]] = None
    # `on_start(session_id, turn)`: a job was registered together with the question it answers (`turn=` of
    # register_job: user_mid, user_message, user_text, brain). The host writes the row that `on_finish` closes.
    on_start: Optional[Callable[[str, dict], None]] = None

    def __init__(self) -> None:
        self._clients: Dict[str, _Client] = {}
        self._jobs: Dict[str, ChatJob] = {}
        self._stop_epochs: Dict[str, int] = {}
        self._waiters: Dict[str, set[asyncio.Task]] = {}
        self._last_tags: Dict[str, str] = {}

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
                     runtime_task_id: str = "", runtime_step_id: str = "", turn: Optional[dict] = None) -> None:
        self._jobs[session_id] = ChatJob(
            task=task, tag=tag,
            runtime_task_id=runtime_task_id, runtime_step_id=runtime_step_id,
        )
        if session_id and tag:
            self._last_tags.pop(session_id, None)
            self._last_tags[session_id] = tag
            while len(self._last_tags) > 2000:
                self._last_tags.pop(next(iter(self._last_tags)), None)
        # Before the task can run (no await since it was created), so the row exists before the job can end.
        if turn is not None and self.on_start is not None:
            try:
                self.on_start(session_id, turn)
            except Exception:  # noqa: BLE001 - bookkeeping must not keep a turn from starting
                pass
        task.add_done_callback(lambda done, sid=session_id: self._job_over(sid, done))

    def _job_over(self, session_id: str, task: asyncio.Task) -> None:
        """A job is over. Skipped when a NEWER job of the same session is already registered: its row in the ledger
        belongs to that newer turn, and the old turn must not close it."""
        job = self._jobs.get(session_id)
        if job is not None and job.task is not task and not job.task.done():
            return
        if self.on_finish is not None:
            try:
                self.on_finish(session_id)
            except Exception:  # noqa: BLE001 - bookkeeping must not break the loop's callbacks
                pass

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

    def stop_epoch(self, session_id: str) -> int:
        """Return the monotonic stop counter for `session_id` (0 if never stopped)."""
        sid = str(session_id or "")
        return self._stop_epochs.get(sid, 0) if sid else 0

    def register_waiter(self, session_id: str, task: Optional[asyncio.Task]) -> int:
        """Track a continuation waiter task for `session_id`, remove it when done, and return current epoch."""
        sid = str(session_id or "")
        if sid and task is not None:
            self._waiters.setdefault(sid, set()).add(task)

            def _discard(done: asyncio.Task, s: str = sid) -> None:
                bucket = self._waiters.get(s)
                if bucket is not None:
                    bucket.discard(done)
                    if not bucket:
                        self._waiters.pop(s, None)

            if task.done():
                _discard(task)
            else:
                task.add_done_callback(_discard)
        return self.stop_epoch(sid)

    def _bump_stop_and_cancel_waiters(self, session_id: str) -> None:
        sid = str(session_id or "")
        if not sid:
            return
        self._stop_epochs[sid] = self._stop_epochs.get(sid, 0) + 1
        for waiter in self._waiters.pop(sid, set()):
            if not waiter.done():
                waiter.cancel()

    def sessions_matching(self, tag_prefix: str) -> list[str]:
        """Return session ids whose active job or orphan waiter matches `tag_prefix`."""
        pfx = str(tag_prefix or "")
        sids = [sid for sid, job in list(self._jobs.items()) if job.tag.startswith(pfx)]
        seen = set(sids)
        for sid in list(self._waiters):
            if sid in seen or sid in self._jobs:
                continue
            stem = f"chat:{sid[:12]}:"
            last = self._last_tags.get(sid, "")
            if (pfx in ("", "chat", "chat:") or stem.startswith(pfx)
                    or pfx.startswith(stem) or (last and last.startswith(pfx))):
                sids.append(sid)
        return sids

    def cancel_session(self, session_id: str) -> Optional[str]:
        """Increment stop epoch, cancel queued waiters, and cancel the active job for `session_id`."""
        self._bump_stop_and_cancel_waiters(session_id)
        job = self.get_job(session_id)
        if not job:
            return None
        if not job.task.done():
            job.task.cancel()
        return job.tag

    def cancel_matching(self, tag_prefix: str) -> list[str]:
        """Cancel matching jobs, increment their stop epochs, and cancel their queued waiters."""
        pfx = str(tag_prefix or "")
        tags: list[str] = []
        for sid in self.sessions_matching(pfx):
            job = self._jobs.get(sid)
            if job and job.tag.startswith(pfx):
                tags.append(job.tag)
                if not job.task.done():
                    job.task.cancel()
            self._bump_stop_and_cancel_waiters(sid)
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
                    _xep_hang(c.backlog, event)
                continue
            sends.append(self._send(cid, c, event))
        if sends:
            # Healthy pages finish well inside the wait, so a caller still sees its event delivered when this returns.
            await asyncio.wait(sends, timeout=SEND_WAIT_S)
