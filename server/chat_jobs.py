"""Async chat turns: start a /chat turn now, fetch the answer later (#1021).

`POST /chat` holds the HTTP request open for the whole turn, often 2 to 5 minutes for an agent with
skills and web tools. A caller on a serverless host pays for every second of that wait, and a dropped
connection loses an answer Javis already finished. `POST /chat/jobs` runs the SAME turn as a background
task and answers at once with a job id; `GET /chat/jobs/{id}` reports the status and, once done, the
same payload `/chat` returns.

Rules this module enforces:
- A job belongs to whoever started it (`owner`: one API token, or the signed-in owner). Another owner
  reading the id gets nothing, which the route turns into a 404, the same answer as an unknown id.
- At most `MAX_RUNNING_PER_OWNER` jobs run at once per owner. Without a cap one script could start a
  hundred agent turns in a second, where `/chat` limited itself by holding one connection per turn.
- One running job per conversation lane (session plus agent). Two turns writing the same session at
  once would interleave their history.
- Finished jobs are kept `JOB_TTL` seconds, and at most `MAX_STORED` of them, in one JSON file under
  STATE_DIR, so the file cannot grow without bound.
- A job still marked running after a restart is reported as an error: the task died with the old
  process, and the caller has to ask again.

No callback URL on purpose: Javis POSTing to an address a caller supplies is a server-side request
forgery risk that needs its own review (blocked private ranges, signed bodies). Polling covers the need.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

JOB_TTL = 24 * 3600
MAX_RUNNING_PER_OWNER = 4
MAX_STORED = 500
# Identifies this process. A running job stamped with another boot id was cut off by a restart.
BOOT_ID = secrets.token_hex(8)

RESTART_ERROR = "interrupted by a server restart, send the message again"


class ChatJobs:
    """The job store plus the background tasks that fill it. One instance per server process."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._jobs: Optional[dict] = None
        # Strong references: the event loop keeps only weak ones, so an unreferenced task can be
        # garbage collected mid-turn.
        self._tasks: set = set()

    # ------------------------------------------------------------------ storage
    def _load(self) -> dict:
        if self._jobs is not None:
            return self._jobs
        jobs = {}
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    jobs = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            jobs = {}
        now = time.time()
        for job in jobs.values():
            if job.get("status") == "running" and job.get("boot") != BOOT_ID:
                job.update(status="error", error=RESTART_ERROR, finished_at=now)
        self._jobs = jobs
        self._prune(now)
        self._save()
        return jobs

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._jobs or {}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            # The in-memory copy still answers; only a restart would forget these jobs.
            pass

    def _prune(self, now: float) -> None:
        jobs = self._jobs or {}
        for job_id in [k for k, v in jobs.items()
                       if v.get("status") != "running" and now - float(v.get("finished_at") or 0) > JOB_TTL]:
            jobs.pop(job_id, None)
        finished = sorted((v.get("finished_at") or 0, k) for k, v in jobs.items() if v.get("status") != "running")
        excess = len(jobs) - MAX_STORED
        for _, job_id in finished[:max(0, excess)]:
            jobs.pop(job_id, None)

    # ------------------------------------------------------------------ public API
    def start(self, owner: str, lane: str, runner: Callable[[], Awaitable[dict]]):
        """Start `runner` in the background. Returns (job_id, "") or ("", reason).

        `reason` is "busy_owner" (too many running jobs for this owner) or "busy_lane" (this
        conversation already has a running job). `runner` returns the `/chat` payload dict.
        """
        now = time.time()
        with self._lock:
            jobs = self._load()
            running = [v for v in jobs.values() if v.get("status") == "running"]
            if sum(1 for v in running if v.get("owner") == owner) >= MAX_RUNNING_PER_OWNER:
                return "", "busy_owner"
            if any(v.get("lane") == lane for v in running):
                return "", "busy_lane"
            job_id = "cj_" + secrets.token_urlsafe(16)
            jobs[job_id] = {"owner": owner, "lane": lane, "status": "running", "boot": BOOT_ID,
                            "created_at": now, "finished_at": None}
            self._prune(now)
            self._save()
        task = asyncio.get_running_loop().create_task(self._run(job_id, runner))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id, ""

    async def _run(self, job_id: str, runner: Callable[[], Awaitable[dict]]) -> None:
        try:
            payload = await runner()
            if not isinstance(payload, dict):
                raise TypeError("runner returned no payload")
            if payload.get("ok"):
                update = {"status": "done", "result": {k: payload.get(k) for k in ("text", "session", "files", "ctx_path")}}
            else:
                # A failed turn: /chat answers 200 with ok=false and the reason in `text`.
                update = {"status": "error", "error": str(payload.get("text") or "turn failed"),
                          "result": {"session": payload.get("session") or ""}}
        except asyncio.CancelledError:
            update = {"status": "error", "error": "cancelled"}
            self._finish(job_id, update)
            raise
        except Exception as exc:  # noqa: BLE001 - the caller must see why, not a job stuck on running
            update = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        self._finish(job_id, update)

    def _finish(self, job_id: str, update: dict) -> None:
        with self._lock:
            jobs = self._load()
            job = jobs.get(job_id)
            if job is None:
                return
            job.update(update, finished_at=time.time())
            self._save()

    def get(self, owner: str, job_id: str) -> Optional[dict]:
        """The public view of a job, or None when it does not exist, expired, or is someone else's."""
        with self._lock:
            jobs = self._load()
            job = jobs.get(str(job_id or ""))
            if not job or not secrets.compare_digest(str(job.get("owner") or ""), str(owner or "")):
                return None
            if job.get("status") != "running" and time.time() - float(job.get("finished_at") or 0) > JOB_TTL:
                return None
            view = {"job_id": job_id, "status": job.get("status"),
                    "created_at": job.get("created_at"), "finished_at": job.get("finished_at")}
            if job.get("status") == "done":
                view.update(job.get("result") or {})
            elif job.get("status") == "error":
                view["error"] = job.get("error") or ""
                view.update(job.get("result") or {})
            return view
