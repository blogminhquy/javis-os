"""Vòng đời chat web độc lập với vòng đời WebSocket.

Một lượt chat là job của server. WebSocket chỉ là subscriber để nhận sự kiện,
vì vậy đóng/F5 tab không được phép huỷ job đang chạy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional


Writer = Callable[[dict], Awaitable[None]]


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
        self._clients: Dict[str, Writer] = {}
        self._jobs: Dict[str, ChatJob] = {}

    def add_client(self, client_id: str, writer: Writer) -> None:
        self._clients[client_id] = writer

    def remove_client(self, client_id: str) -> None:
        self._clients.pop(client_id, None)

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

        writers = list(self._clients.values())
        if writers:
            await asyncio.gather(*(writer(event) for writer in writers),
                                 return_exceptions=True)
