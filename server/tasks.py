"""Autonomous task queue and dispatcher for Javis OS.

This module treats Kanban as an agent runtime, not a manual Trello board:

* SQLite is the lifecycle source of truth.
* A dedicated dispatcher scans every registered brain.
* Claims are atomic and workers run as independent asyncio tasks.
* Every run has a lease, heartbeat, attempt record and event history.
* New goals pass through a lightweight AI specification stage before execution.
* Claude, Codex and API/OpenRouter workers share the auxiliary-engine adapter.

The legacy ``Javis/kanban.json`` file is imported once and then maintained as a
readable snapshot so older installations and brain backups keep working.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from fastapi import APIRouter, Form, Query

from claude_cli import claude_engine, cancel_all, _empty_mcp_file
import aux_engine
import channel_context
from task_store import TaskStore, VALID_STATUS


LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20
DISPATCH_INTERVAL_SECONDS = 5
MAX_RESULT_CHARS = 20_000
SPECIFIER_TIMEOUT_SECONDS = 180
WORKER_TIMEOUT_SECONDS = 900
# Việc đã kết thúc (done/cancelled) quá số ngày này tự chuyển archived (rời bảng, còn tra được).
ARCHIVE_TERMINAL_AFTER_DAYS = 3.0
CAPABILITIES = {"auto", "files", "research", "mcp-read", "code", "external-write"}
EXECUTION_MODES = {"suggest", "auto", "full"}


@dataclass
class TasksDeps:
    brain_root: Callable[[str], str]
    atomic_write_text: Callable[[Any, str], None]
    execute_workflow: Callable
    workflows_dir: Callable[[str], Path]
    build_system_prompt: Callable[[str], str]
    aux_model: Callable[[], Optional[str]]
    safe_tools: List[str]
    state_dir: Optional[Path] = None
    scheduler_brains: Optional[Callable[[], List[str]]] = None
    apply_mcp: Optional[Callable] = None
    mcp_allow_patterns: Optional[Callable[[], List[str]]] = None
    report: Optional[Callable] = None
    aux_swap: Optional[Callable] = None


class TasksFeature:
    def __init__(self, deps: TasksDeps):
        self.deps = deps
        state_dir = Path(deps.state_dir or Path(__file__).parent)
        self.store = TaskStore(state_dir / "kanban.sqlite3")
        self.max_workers = max(1, min(8, int(os.getenv("JAVIS_KANBAN_MAX_WORKERS", "2"))))
        self._workers: dict[str, asyncio.Task] = {}
        self._worker_ids: dict[str, str] = {}
        self._worker_brains: dict[str, str] = {}
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._wake = asyncio.Event()
        self._closing = False
        self._snap_locks: dict[str, asyncio.Lock] = {}
        self.router = self._make_router()

    # ------------------------------------------------------------------
    # Board identity, migration and portable snapshot
    # ------------------------------------------------------------------
    def _root(self, brain: str) -> str:
        return str(Path(self.deps.brain_root(brain)).resolve())

    def _legacy_path(self, root: str) -> Path:
        return Path(root) / "Javis" / "kanban.json"

    def _ensure(self, brain: str) -> str:
        root = self._root(brain)
        self.store.import_legacy(root, self._legacy_path(root))
        return root

    def _brain_roots(self) -> list[str]:
        values: list[str] = []
        if self.deps.scheduler_brains:
            try:
                values.extend(self.deps.scheduler_brains() or [])
            except Exception:
                pass
        values.extend(self.store.board_roots())
        roots: list[str] = []
        seen: set[str] = set()
        for value in values:
            try:
                root = self._root(value)
            except Exception:
                continue
            if root in seen or not Path(root).is_dir():
                continue
            seen.add(root)
            self.store.import_legacy(root, self._legacy_path(root))
            roots.append(root)
        return roots

    def _snapshot(self, root: str) -> None:
        """Mirror runtime state to JSON for old builds and brain backup."""
        try:
            tasks = self.store.list_tasks(root, include_archived=True, limit=5000)
            # MỘT truy vấn cho mọi task thay vì một truy vấn mỗi task (N+1). Với bảng đầy
            # tới trần 5000 thì đây là 5000 lượt round-trip sqlite biến thành 10 lượt.
            events = self.store.list_events_bulk([t["id"] for t in tasks], 20)
            for task in tasks:
                task["log"] = [
                    {
                        "ts": time.strftime(
                            "%Y-%m-%d %H:%M",
                            time.localtime(float(event.get("created_at") or 0)),
                        ),
                        "msg": event.get("message") or event.get("event_type") or "",
                    }
                    for event in events.get(task["id"], [])
                ]
                task.pop("normalized_title", None)
            data = {
                "schema": 2,
                "source": "kanban.sqlite3",
                "orchestration": self.store.board_mode(root),
                "tasks": tasks,
                "updated": time.time(),
            }
            self.deps.atomic_write_text(
                self._legacy_path(root),
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            print(f"[kanban snapshot] {type(exc).__name__}: {exc}", file=__import__("sys").stderr)

    async def _asnapshot(self, root: str) -> None:
        """_snapshot cho nơi gọi async: đẩy ra thread, nhưng SERIAL theo từng brain.

        Vì sao cần khoá: _snapshot đọc cả bảng rồi ghi đè file mirror. Hai lần chạy song
        song đều ghi ra file hợp lệ, nhưng lần CŨ có thể hạ cánh sau lần MỚI và để lại
        bản thiu cho tới lần thay đổi kế tiếp. Bản đồng bộ trước đây tự nối tiếp nên
        không có vấn đề này; đẩy ra thread mà quên khoá là tự tạo ra nó.
        """
        lock = self._snap_locks.get(root)
        if lock is None:
            lock = self._snap_locks[root] = asyncio.Lock()
        async with lock:
            await asyncio.to_thread(self._snapshot, root)

    # ------------------------------------------------------------------
    # Public generator API used by Learn/chat
    # ------------------------------------------------------------------
    def enqueue(
        self,
        brain: str,
        title: str,
        intent: str,
        route: str = "auto",
        priority: int = 2,
        deps: Optional[List[str]] = None,
        needs_approval: bool = False,
        created_by: str = "user",
        chat_id: str = "",
        capability: str = "auto",
        execution_mode: str = "auto",
        idempotency_key: str = "",
    ) -> str:
        root = self._ensure(brain)
        status = "todo" if deps else "triage"
        tid = self.store.enqueue(
            root,
            title,
            intent,
            route,
            priority,
            deps,
            needs_approval,
            created_by,
            chat_id,
            capability if capability in CAPABILITIES else "auto",
            execution_mode if execution_mode in EXECUTION_MODES else "auto",
            idempotency_key,
            status,
        )
        self.store.promote_dependencies(root)
        self._snapshot(root)
        self.wake()
        return tid

    # ------------------------------------------------------------------
    # Dedicated dispatcher
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._dispatcher_task and not self._dispatcher_task.done():
            return
        for root in self._brain_roots():
            if self.store.recover_codex_global_flag_blocks(root):
                self._snapshot(root)
        self._closing = False
        self._dispatcher_task = asyncio.create_task(
            self._dispatcher_loop(), name="javis-kanban-dispatcher"
        )
        self.wake()

    async def shutdown(self) -> None:
        self._closing = True
        self._wake.set()
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
        for task in list(self._workers.values()):
            task.cancel()
        if self._workers:
            await asyncio.gather(*list(self._workers.values()), return_exceptions=True)
        if self._dispatcher_task:
            await asyncio.gather(self._dispatcher_task, return_exceptions=True)
        self._workers.clear()
        self.store.close()

    def wake(self) -> None:
        self._wake.set()

    async def tick(self, brains: Optional[List[str]] = None) -> None:
        """Compatibility hook for the old 30-second scheduler.

        It only registers/migrates boards and wakes the independent dispatcher. It
        never waits for a model run, so reminders and cron cannot be delayed.
        """
        for brain in brains or []:
            try:
                root = self._ensure(brain)
                self._housekeep(root)
            except Exception as exc:
                print(f"[kanban tick] {type(exc).__name__}: {exc}", file=__import__("sys").stderr)
        self.wake()

    async def _dispatcher_loop(self) -> None:
        while not self._closing:
            try:
                await self._dispatch_available()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(
                    f"[kanban dispatcher] {type(exc).__name__}: {exc}",
                    file=__import__("sys").stderr,
                )
            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=DISPATCH_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def _housekeep(self, root: str) -> None:
        active = set(self._worker_ids.values())
        changed = self.store.reclaim_stale(root, active)
        changed += self.store.promote_dependencies(root)
        # Việc một-lần đã xong/huỷ quá hạn tự rời bảng (archived) - bảng Việc chỉ giữ
        # việc còn sống và việc mới kết thúc gần đây, lịch sử vẫn tra được khi cần.
        changed += self.store.archive_old_terminal(root, ARCHIVE_TERMINAL_AFTER_DAYS)
        if changed:
            self._snapshot(root)

    async def _dispatch_available(self) -> None:
        self._prune_workers()
        slots = self.max_workers - len(self._workers)
        if slots <= 0:
            return

        candidates: list[dict] = []
        for root in self._brain_roots():
            self._housekeep(root)
            if self.store.board_mode(root) != "auto":
                continue
            task = self.store.next_candidate(root)
            if task:
                candidates.append(task)
        candidates.sort(
            key=lambda t: (
                0 if t.get("status") == "triage" else 1,
                int(t.get("priority") or 2),
                float(t.get("created_at") or 0),
            )
        )
        for task in candidates[:slots]:
            await self._claim_and_spawn(task["id"])

    def _prune_workers(self) -> None:
        for tid, worker in list(self._workers.items()):
            if worker.done():
                self._workers.pop(tid, None)
                self._worker_ids.pop(tid, None)
                self._worker_brains.pop(tid, None)

    async def _claim_and_spawn(self, task_id: str) -> bool:
        if task_id in self._workers and not self._workers[task_id].done():
            return False
        current = self.store.get_task(task_id)
        if not current:
            return False
        worker_id = f"worker:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        provider = str(aux_engine.read_spec().get("provider") or "")
        claimed = self.store.claim(
            task_id, worker_id, LEASE_SECONDS, engine_provider=provider
        )
        if not claimed:
            return False
        root = str(claimed["brain_root"])
        worker = asyncio.create_task(
            self._run_worker(claimed, worker_id),
            name=f"javis-task-{task_id}",
        )
        self._workers[task_id] = worker
        self._worker_ids[task_id] = worker_id
        self._worker_brains[task_id] = root
        worker.add_done_callback(lambda _task, tid=task_id: self._worker_done(tid))
        await self._asnapshot(root)
        return True

    def _worker_done(self, task_id: str) -> None:
        root = self._worker_brains.get(task_id, "")
        self._workers.pop(task_id, None)
        self._worker_ids.pop(task_id, None)
        self._worker_brains.pop(task_id, None)
        if root:
            self._snapshot(root)
        self.wake()

    async def _heartbeat(self, task_id: str, worker_id: str) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if not self.store.heartbeat(task_id, worker_id, LEASE_SECONDS):
                return

    async def _run_worker(self, task: dict, worker_id: str) -> None:
        tid = str(task["id"])
        root = str(task["brain_root"])
        heartbeat = asyncio.create_task(
            self._heartbeat(tid, worker_id), name=f"javis-heartbeat-{tid}"
        )
        final_task: Optional[dict] = None
        try:
            # New goals first pass through an AI specifier. This keeps raw Learn
            # suggestions out of the executable queue.
            if (task.get("capability") or "auto") == "auto":
                spec, error = await asyncio.wait_for(
                    self._specify(task), timeout=SPECIFIER_TIMEOUT_SECONDS
                )
                if error:
                    final_task = self.store.block(
                        tid, worker_id, "transient", error, transient=True
                    )
                else:
                    final_task = self.store.prepared(
                        tid,
                        worker_id,
                        spec["intent"],
                        spec["capability"],
                        spec["execution_mode"],
                        metadata={
                            "acceptance": spec.get("acceptance", []),
                            "specifier": spec.get("specifier", "ai"),
                        },
                    )
                return

            if (
                task.get("capability") == "external-write"
                and task.get("execution_mode") != "full"
            ):
                final_task = self.store.block(
                    tid,
                    worker_id,
                    "capability",
                    "Task cần hành động ra ngoài. Chỉ worker mode=full mới được thực thi.",
                )
                return

            result, error, needs_input, metadata = await asyncio.wait_for(
                self._execute(task), timeout=WORKER_TIMEOUT_SECONDS
            )
            if error:
                final_task = self.store.block(
                    tid,
                    worker_id,
                    "transient",
                    error,
                    result=result,
                    transient=self._is_transient(error),
                )
            elif needs_input:
                final_task = self.store.block(
                    tid,
                    worker_id,
                    "needs_input",
                    self._needs_input_reason(result),
                    result=result,
                )
            else:
                final_task = self.store.complete(
                    tid,
                    worker_id,
                    result,
                    needs_approval=bool(task.get("needs_approval")),
                    metadata=metadata,
                    artifacts=self._artifacts(result, root),
                )
                self.store.promote_dependencies(root)
        except asyncio.CancelledError:
            self.store.cancel_running(tid, "worker cancelled")
            raise
        except Exception as exc:
            final_task = self.store.block(
                tid,
                worker_id,
                "transient",
                f"{type(exc).__name__}: {exc}",
                transient=True,
            )
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            await self._asnapshot(root)
            if final_task and final_task.get("status") in ("done", "review", "blocked"):
                await self._report(final_task)

    # ------------------------------------------------------------------
    # AI specification and execution lanes
    # ------------------------------------------------------------------
    def _base_cli(
        self,
        task: dict,
        allowed_tools: Optional[list[str]],
        mode: str,
        tag_suffix: str,
    ):
        root = str(task["brain_root"])
        cli = claude_engine(
            system_prompt=self.deps.build_system_prompt(root),
            cwd=root,
            tag=f"dispatch:{task['id']}:{tag_suffix}",
            allowed_tools=allowed_tools,
        )
        cli.javis_vault = root
        cli.javis_mode = mode
        if self.deps.apply_mcp and mode in ("auto", "full"):
            try:
                self.deps.apply_mcp(cli, mode=mode, brain=root)
            except Exception:
                pass
        elif allowed_tools is not None:
            mcp_file = _empty_mcp_file()
            if mcp_file:
                cli.mcp_config = mcp_file
                cli.mcp_strict = True
        cli = aux_engine.apply(self.deps, cli, mode=mode, tag=cli.tag)
        try:
            cli.max_wall_s = 600
        except Exception:
            pass
        return cli

    async def _query(self, cli, prompt: str) -> tuple[str, str, list[str]]:
        if not cli.is_available():
            spec = aux_engine.read_spec()
            return "", f"Engine {spec.get('provider') or 'AI'} chưa sẵn sàng", []
        # Gom RIÊNG câu chốt (final) và dòng tường thuật (text). Trước đây trộn chung nên
        # result = toàn bộ dòng suy nghĩ của worker ("Tôi sẽ lần theo...", "Lệnh shell bị
        # chặn...") rồi đổ nguyên si về Telegram. Có final thì final LÀ kết quả; text chỉ
        # là lối thoát cho engine không phát final.
        final = ""
        narration: list[str] = []
        error = ""
        tool_calls: list[str] = []
        try:
            async for event in cli.query(prompt):
                kind = event.get("type")
                if kind == "final":
                    final = str(event.get("content") or "") or final
                elif kind == "text":
                    narration.append(str(event.get("content") or ""))
                elif kind == "tool_call":
                    name = str(event.get("name") or event.get("tool") or "")
                    if name:
                        tool_calls.append(name)
                elif kind == "error":
                    error = str(event.get("content") or "engine error")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        out = final.strip() or "\n".join(v for v in narration if v).strip()
        return out, error, tool_calls

    async def _specify(self, task: dict) -> tuple[dict, str]:
        cli = self._base_cli(task, [], "suggest", "specifier")
        prompt = f"""
Bạn là specifier của hàng đợi AI Javis. Chuẩn hoá goal dưới đây thành một task có thể
chạy headless. Không thực thi task, không hỏi người dùng, không thêm mục tiêu ngoài phạm vi.

Tiêu đề: {task.get('title', '')}
Goal thô:
{task.get('intent', '')}

Chọn đúng một capability:
- files: đọc/ghi/sắp xếp nội dung trong brain
- research: cần tìm hiểu web hoặc tổng hợp nguồn
- mcp-read: cần đọc dữ liệu thật từ connector/MCP
- code: cần sửa hoặc kiểm thử code
- external-write: gửi tin, tạo lịch/đơn/bài đăng hoặc thay đổi hệ thống bên ngoài

Trả duy nhất JSON hợp lệ, không markdown:
{{
  "intent": "mô tả đầu ra cụ thể và đủ ngữ cảnh",
  "capability": "files|research|mcp-read|code|external-write",
  "execution_mode": "suggest|auto|full",
  "acceptance": ["điều kiện hoàn thành 1", "điều kiện hoàn thành 2"]
}}

Luật quyền: files/research/mcp-read/code dùng auto. external-write chỉ dùng full nếu goal
nói rõ đã được phép tự hành động; nếu không thì để auto để kernel chặn và xin quyền.
""".strip()
        out, error, _ = await self._query(cli, prompt)
        if error:
            # Deterministic fallback keeps the queue moving when a cheap auxiliary
            # model is unavailable.
            return self._heuristic_spec(task), ""
        parsed = self._extract_json(out)
        if not isinstance(parsed, dict):
            return self._heuristic_spec(task), ""
        capability = str(parsed.get("capability") or "files")
        if capability not in CAPABILITIES or capability == "auto":
            capability = "files"
        mode = str(parsed.get("execution_mode") or "auto")
        if mode not in EXECUTION_MODES:
            mode = "auto"
        if capability == "external-write" and mode == "full":
            raw = (str(task.get("intent") or "") + " " + str(task.get("title") or "")).lower()
            permission_words = (
                "toàn quyền", "full quyền", "tự gửi", "tự đăng", "tự tạo",
                "không cần hỏi", "được phép thực hiện",
            )
            if not any(word in raw for word in permission_words):
                mode = "auto"
        return {
            "intent": str(parsed.get("intent") or task.get("intent") or task.get("title") or ""),
            "capability": capability,
            "execution_mode": mode,
            "acceptance": parsed.get("acceptance") if isinstance(parsed.get("acceptance"), list) else [],
            "specifier": "ai",
        }, ""

    def _heuristic_spec(self, task: dict) -> dict:
        text = (
            str(task.get("title") or "") + " " + str(task.get("intent") or "")
        ).lower()
        capability = "files"
        if any(k in text for k in ("github", "code", "mã nguồn", "test", "bug", "deploy")):
            capability = "code"
        elif any(k in text for k in ("gửi ", "đăng ", "tạo lịch", "tạo đơn", "thanh toán")):
            capability = "external-write"
        elif any(k in text for k in ("mcp", "doanh thu", "calendar", "lịch", "email", "pos")):
            capability = "mcp-read"
        elif any(k in text for k in ("tìm hiểu", "nghiên cứu", "web", "website")):
            capability = "research"
        return {
            "intent": str(task.get("intent") or task.get("title") or ""),
            "capability": capability,
            "execution_mode": "auto",
            "acceptance": [],
            "specifier": "heuristic",
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        value = (text or "").strip()
        candidates = [value]
        match = re.search(r"\{[\s\S]*\}", value)
        if match:
            candidates.append(match.group(0))
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return None

    def _lane_tools(self, task: dict) -> tuple[list[str], str, list[str]]:
        capability = str(task.get("capability") or "files")
        mode = str(task.get("execution_mode") or "auto")
        tools = list(self.deps.safe_tools)
        disallowed = ["Task"]
        if capability == "code":
            tools.append("Bash")
            disallowed.extend(["WebFetch", "WebSearch"])
        elif capability == "research":
            tools.extend(["WebFetch", "WebSearch"])
            disallowed.append("Bash")
        elif capability == "mcp-read":
            if self.deps.mcp_allow_patterns:
                try:
                    tools.extend(self.deps.mcp_allow_patterns() or [])
                except Exception:
                    pass
            disallowed.extend(["Bash", "WebFetch", "WebSearch"])
        elif capability == "external-write":
            if self.deps.mcp_allow_patterns:
                try:
                    tools.extend(self.deps.mcp_allow_patterns() or [])
                except Exception:
                    pass
            disallowed.extend(["Bash", "WebFetch", "WebSearch"])
        else:
            disallowed.extend(["Bash", "WebFetch", "WebSearch"])
        return list(dict.fromkeys(tools)), mode, disallowed

    async def _execute(self, task: dict) -> tuple[str, str, bool, dict]:
        route = str(task.get("route") or "auto").strip()
        intent = str(task.get("intent") or task.get("title") or "")
        tools, mode, disallowed = self._lane_tools(task)

        if route.startswith("wf:"):
            slug = route[3:].strip()
            result = ""
            error = ""
            try:
                async for event in self.deps.execute_workflow(
                    task["brain_root"], slug, intent, tools
                ):
                    kind = event.get("type")
                    if kind == "done":
                        result = event.get("result") or result
                    elif kind == "wait_user":
                        # Workflow dừng chờ người duyệt. Không có nhánh này thì task bị
                        # chấm là XONG với kết quả rỗng, và việc cần duyệt biến mất.
                        result = (result or "") + (
                            "\n[[NEEDS_INPUT]] Workflow dừng chờ duyệt bước "
                            f"'{event.get('node') or '?'}'"
                            f"{': ' + str(event.get('prompt')) if event.get('prompt') else ''}"
                        )
                    elif kind == "escalation":
                        result = (result or "") + (
                            "\n[[NEEDS_INPUT]] Agent chuyển lại cho người: "
                            f"{event.get('reason') or 'không rõ lý do'}"
                        )
                    elif kind in ("error", "step_error"):
                        error = event.get("content") or error
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            return (
                result,
                error,
                "[[NEEDS_INPUT]]" in (result or ""),
                {"route": route, "capability": task.get("capability")},
            )

        cli = self._base_cli(task, tools, mode, "execute")
        try:
            cli.disallowed_tools = disallowed
        except Exception:
            pass
        acceptance = task.get("metadata", {}).get("acceptance") or []
        prompt = f"""
Bạn là autonomous worker của Javis. Hãy hoàn thành đúng task được giao trong brain đã
ghim. Tự kiểm tra kết quả trước khi kết thúc. Không mở rộng phạm vi và không hỏi trong
chat vì đây là worker headless.

TASK_ID: {task.get('id')}
CAPABILITY: {task.get('capability')}
MODE: {mode}
MỤC TIÊU:
{intent}

ĐIỀU KIỆN HOÀN THÀNH:
{json.dumps(acceptance, ensure_ascii=False)}

Nếu thiếu một quyết định hoặc dữ liệu mà không thể suy ra an toàn, kết quả phải bắt đầu
bằng [[NEEDS_INPUT]] và nêu đúng một lý do cụ thể. Nếu hoàn thành, báo cáo ngắn: đã làm
gì, dữ liệu/file/artifact nào được tạo và cách đã kiểm chứng.
""".strip()
        result, error, tool_calls = await self._query(cli, prompt)
        return (
            result[:MAX_RESULT_CHARS],
            error,
            "[[NEEDS_INPUT]]" in result,
            {
                "route": route,
                "capability": task.get("capability"),
                "execution_mode": mode,
                "tool_calls": tool_calls[-100:],
                "provider": aux_engine.read_spec().get("provider"),
            },
        )

    @staticmethod
    def _is_transient(error: str) -> bool:
        text = (error or "").lower()
        return any(
            marker in text
            for marker in (
                "timeout", "timed out", "rate limit", "429", "temporar",
                "connection", "network", "busy", "unavailable", "reset",
            )
        )

    @staticmethod
    def _needs_input_reason(result: str) -> str:
        """MỘT ý ngắn đủ đọc trên điện thoại. Worker hay kể lể vài dòng rồi mới nêu điều
        còn thiếu ở CUỐI, nên lấy dòng cuối có nghĩa chứ không phải câu mở đầu."""
        text = (result or "").replace("[[NEEDS_INPUT]]", "").strip()
        lines = [ln.strip(" -•\t") for ln in text.splitlines()]
        lines = [ln for ln in lines if len(ln) > 8]
        if not lines:
            return "Worker cần thêm thông tin để tiếp tục."
        return lines[-1][:200]

    @staticmethod
    def _artifacts(result: str, root: str) -> list[dict]:
        artifacts: list[dict] = []
        root_path = Path(root).resolve()
        seen: set[str] = set()
        for raw in re.findall(r"(?:`|\b)([^`\n]+\.[A-Za-z0-9]{1,8})(?:`|\b)", result or ""):
            value = raw.strip().strip("'\"")
            candidates = [Path(value)]
            if not Path(value).is_absolute():
                candidates.insert(0, root_path / value)
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    if resolved.is_file() and (
                        resolved == root_path or root_path in resolved.parents
                    ):
                        rel = str(resolved.relative_to(root_path)).replace("\\", "/")
                        if rel not in seen:
                            seen.add(rel)
                            artifacts.append({"type": "file", "path": rel})
                        break
                except Exception:
                    continue
        return artifacts[:50]

    async def _report(self, task: dict) -> None:
        if not self.deps.report:
            return
        status = str(task.get("status") or "")
        labels = {
            "review": "đã làm xong, cần duyệt ngoại lệ",
            "done": "đã hoàn thành",
            "blocked": "bị chặn, cần anh xem",
        }
        icon = "✅" if status in ("review", "done") else "⚠"
        parts = [f"{icon} Việc '{task.get('title', '')}' {labels.get(status, status)}."]
        # Tin nhắn PHẢI ngắn - đây là cái liếc trên điện thoại, chi tiết đã nằm ở trang Việc.
        # Việc bị chặn: chỉ cần LÝ DO (result lúc này là tường thuật dở dang, dán vào chỉ
        # tổ thành bức tường văn và lặp lại chính lý do). Việc xong: vài dòng đầu của kết quả.
        if status == "blocked":
            reason = str(task.get("block_reason") or task.get("block_kind") or "").strip()
            parts.append("Lý do: " + (reason[:240] or "không rõ"))
        else:
            head = "\n".join(
                ln for ln in str(task.get("result") or "").strip().splitlines() if ln.strip()
            )[:240].strip()
            if head:
                parts.append(head)
        parts.append("Xem chi tiết ở trang Việc.")
        try:
            await self.deps.report(
                task.get("chat_id", ""),
                channel_context.strip_control_blocks("\n\n".join(parts)),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Views and operator API
    # ------------------------------------------------------------------
    def board_view(self, brain: str) -> dict:
        root = self._ensure(brain)
        tasks = self.store.list_tasks(root)
        columns = {
            name: []
            for name in (
                "triage", "todo", "ready", "running", "review", "blocked", "done",
                "cancelled",
            )
        }
        for task in tasks:
            columns.setdefault(task.get("status", "triage"), []).append(task)
        counts = {status: len(items) for status, items in columns.items()}
        workers = [
            {
                "task_id": tid,
                "worker_id": self._worker_ids.get(tid, ""),
                "brain_root": self._worker_brains.get(tid, ""),
                "alive": not worker.done(),
            }
            for tid, worker in self._workers.items()
            if self._worker_brains.get(tid) == root
        ]
        health = self.store.health(root)
        attention = columns["blocked"] + columns["review"]
        queue = columns["triage"] + columns["todo"] + columns["ready"]
        active = columns["running"]
        history = columns["done"] + columns["cancelled"]
        return {
            "schema": 2,
            "brain_root": root,
            "orchestration": self.store.board_mode(root),
            "dispatcher": {
                "running": bool(self._dispatcher_task and not self._dispatcher_task.done()),
                "max_workers": self.max_workers,
                "active_workers": len(workers),
                "workers": workers,
            },
            "operations": {
                "active": active,
                "attention": attention,
                "queue": queue,
                "history": history,
            },
            "columns": columns,
            "counts": counts,
            "completed_24h": health["completed_24h"],
            "running": bool(workers),
        }

    def _make_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/kanban")
        async def kanban_get(brain: str = Query("brain")):
            return self.board_view(brain)

        @router.get("/kanban/health")
        async def kanban_health(brain: str = Query("brain")):
            view = self.board_view(brain)
            return {
                "orchestration": view["orchestration"],
                "dispatcher": view["dispatcher"],
                "counts": view["counts"],
                "completed_24h": view["completed_24h"],
            }

        @router.get("/kanban/task/show")
        async def kanban_show(id: str = Query(...), brain: str = Query("brain")):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            return {
                "ok": True,
                "task": task,
                "events": self.store.list_events(id, 100),
                "runs": self.store.list_runs(id, 20),
            }

        @router.post("/kanban/task")
        async def kanban_add(
            title: str = Form(...),
            intent: str = Form(""),
            route: str = Form("auto"),
            priority: str = Form("2"),
            deps: str = Form(""),
            needs_approval: str = Form("0"),
            chat_id: str = Form(""),
            brain: str = Form("brain"),
            capability: str = Form("auto"),
            execution_mode: str = Form("auto"),
            idempotency_key: str = Form(""),
        ):
            dep_list = [d.strip() for d in (deps or "").split(",") if d.strip()]
            try:
                value = int(priority)
            except ValueError:
                value = 2
            tid = self.enqueue(
                brain,
                title,
                intent or title,
                route or "auto",
                value,
                dep_list,
                needs_approval in ("1", "true", "True", "on"),
                "user",
                chat_id,
                capability,
                execution_mode,
                idempotency_key,
            )
            return {"ok": True, "id": tid}

        @router.post("/kanban/task/move")
        async def kanban_move(
            id: str = Form(...),
            status: str = Form(...),
            brain: str = Form("brain"),
        ):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            if status not in VALID_STATUS:
                return {"ok": False, "error": "status không hợp lệ"}
            if not self.store.move(id, status):
                return {"ok": False, "error": "không thể chuyển task đang chạy"}
            await self._asnapshot(root)
            self.wake()
            return {"ok": True, "status": status}

        @router.post("/kanban/task/delete")
        async def kanban_delete(
            id: str = Form(...), brain: str = Form("brain")
        ):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            if not self.store.move(id, "archived", "operator archive"):
                return {"ok": False, "error": "không thể archive task đang chạy"}
            await self._asnapshot(root)
            return {"ok": True, "archived": True}

        @router.post("/kanban/purge")
        async def kanban_purge(
            brain: str = Form("brain"), include_done: str = Form("0")
        ):
            """Dọn sạch việc đã kết thúc khỏi bảng. Mặc định chỉ archived + cancelled;
            include_done=1 mới đụng tới done (lịch sử việc làm được)."""
            root = self._ensure(brain)
            statuses = ("archived", "cancelled")
            if str(include_done).strip() in ("1", "true", "True"):
                statuses = statuses + ("done",)
            removed = self.store.purge_terminal(root, statuses=statuses)
            await self._asnapshot(root)
            return {"ok": True, "removed": removed}

        @router.post("/kanban/clear")
        async def kanban_clear(brain: str = Form("brain")):
            """Xoá TRẮNG bảng (trừ việc đang chạy). Dứt khoát, không hoàn tác được."""
            root = self._ensure(brain)
            removed = self.store.clear_board(root)
            await self._asnapshot(root)
            return {"ok": True, "removed": removed}

        @router.post("/kanban/orchestration")
        async def kanban_orchestration(
            mode: str = Form(...), brain: str = Form("brain")
        ):
            if mode not in ("off", "manual", "auto"):
                return {"ok": False, "error": "mode không hợp lệ"}
            root = self._ensure(brain)
            self.store.set_orchestration(root, mode)
            await self._asnapshot(root)
            self.wake()
            return {"ok": True, "orchestration": mode}

        @router.post("/kanban/nudge")
        async def kanban_nudge(brain: str = Form("brain")):
            root = self._ensure(brain)
            self._housekeep(root)
            candidate = self.store.next_candidate(root)
            if not candidate:
                return {"ok": True, "started": False, "note": "không có task sẵn sàng"}
            started = await self._claim_and_spawn(candidate["id"])
            return {"ok": True, "started": started, "id": candidate["id"]}

        @router.post("/kanban/run")
        async def kanban_run_one(
            id: str = Form(...), brain: str = Form("brain")
        ):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            if task.get("status") not in ("triage", "ready"):
                if not self.store.move(id, "ready", "operator run"):
                    return {"ok": False, "error": "task đang chạy"}
            started = await self._claim_and_spawn(id)
            return {"ok": started, "started": started, "id": id}

        @router.post("/kanban/task/retry")
        async def kanban_retry(
            id: str = Form(...), brain: str = Form("brain")
        ):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            if not self.store.move(id, "ready", "operator retry"):
                return {"ok": False, "error": "task đang chạy"}
            await self._asnapshot(root)
            self.wake()
            return {"ok": True, "status": "ready"}

        @router.post("/kanban/task/cancel")
        async def kanban_cancel(
            id: str = Form(...), brain: str = Form("brain")
        ):
            root = self._ensure(brain)
            task = self.store.get_task(id)
            if not task or task.get("brain_root") != root:
                return {"ok": False, "error": "not found"}
            worker = self._workers.get(id)
            if worker and not worker.done():
                cancel_all(f"dispatch:{id}")
                worker.cancel()
            elif not self.store.move(id, "cancelled", "operator cancel"):
                return {"ok": False, "error": "không thể huỷ"}
            await self._asnapshot(root)
            return {"ok": True, "cancelled": True}

        @router.post("/kanban/stop")
        async def kanban_stop(brain: str = Form("brain")):
            root = self._ensure(brain)
            self.store.set_orchestration(root, "off")
            cancelled = 0
            for tid, worker in list(self._workers.items()):
                if self._worker_brains.get(tid) != root or worker.done():
                    continue
                cancel_all(f"dispatch:{tid}")
                worker.cancel()
                cancelled += 1
            await self._asnapshot(root)
            return {"ok": True, "orchestration": "off", "cancelled": cancelled}

        return router


# Bản đang chạy, để CODE TRONG CÙNG TIẾN TRÌNH gọi tới hàng đợi mà không phải đi vòng qua HTTP.
# Người dùng đầu tiên: plugin `javis-task` - nó chạy in-process nên gọi thẳng `enqueue()` được.
#
# Vì sao không cho plugin POST /kanban/task như javis-schedule vẫn POST /reminders: đường đó đòi
# đăng nhập, và cách duy nhất để mở là thêm nó vào `_AUTH_LOCAL_EXACT` (danh sách miễn auth cho
# localhost). Làm vậy nghĩa là BẤT KỲ tiến trình nào trên cùng máy chủ cũng giao được việc cho
# Javis mà không cần credential - một lỗ hổng thật, chỉ để tránh ba dòng code này.
_FEATURE: Optional["TasksFeature"] = None


def current() -> Optional["TasksFeature"]:
    """Hàng đợi đang chạy, hoặc None nếu chưa register (test nạp lẻ module này)."""
    return _FEATURE


def register(app, deps: TasksDeps) -> TasksFeature:
    global _FEATURE
    feature = TasksFeature(deps)
    app.include_router(feature.router)
    _FEATURE = feature
    return feature
