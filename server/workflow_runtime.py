"""Adaptive Runtime Phase 10: chạy workflow như capability graph, có checkpoint.

Điểm mấu chốt của phase này KHÔNG phải là viết một engine workflow mới. Runner cũ đã
chạy được prompt chain; cái nó thiếu là TRẠNG THÁI. Task Kanban chạy workflow mà tiến
trình chết là chạy lại từ bước 0, kể cả những bước đã ghi ra ngoài. Phase 10 bọc đúng
định dạng cũ vào cỗ máy đồ thị + checkpoint của runtime mới, giữ nguyên engine, giữ
nguyên prompt, giữ nguyên bộ event mà dashboard đang nghe.

Ba bất biến của phase này:

1. **Node đã xong không chạy lại.** Resume đọc checkpoint, node `COMPLETED` giữ nguyên
   output cũ. Với node ghi thì đây là ranh giới không được phép sai.
2. **Node ghi không bao giờ tự chạy.** Workflow chạy nền không có ai để hỏi, nên gặp
   node ghi là dừng ở `WAITING_USER` và trả quyền quyết định về người dùng. Đây là lý
   do `wait_user` nằm trong danh sách node kind của spec.
3. **Workflow con ghim theo revision.** Gọi workflow con mà không ghim revision thì
   lineage vô nghĩa và resume không tái lập được, nên tầng đồ thị bắt buộc trường này.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import context_runtime
import secrets_store
import workflow_graph
from workflow_graph import WorkflowGraph, WorkflowNode

WORKFLOW_POLICY_VERSION = "workflow-graph-canary-v1"
STATE_SCHEMA_VERSION = "workflow-state-v1"

# Executor của một node: nhận (node, prompt đã nội suy) -> (text, events).
NodeExecutor = Callable[[WorkflowNode, str], Awaitable[dict]]
# Chạy một node capability. `approved` chỉ True khi người dùng đã duyệt đúng mã.
CapabilityRunner = Callable[[WorkflowNode, bool], Awaitable[dict]]
GraphLoader = Callable[[str], Optional[WorkflowGraph]]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _pending_code(task_id: str, node: WorkflowNode) -> str:
    """Mã duyệt suy ra từ task + node + arguments, không phải số ngẫu nhiên."""
    digest = _sha({"task": str(task_id or ""), "node": node.id,
                   "capability": node.capability_name or node.capability_id,
                   "arguments": node.arguments})
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    value = int(digest[:16], 16)
    out = []
    for _ in range(6):
        value, index = divmod(value, len(alphabet))
        out.append(alphabet[index])
    return "".join(out)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class WorkflowPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    allowed_slugs: tuple[str, ...]
    max_nodes: int
    max_parallel: int
    node_timeout_seconds: float
    max_nesting_depth: int
    allow_write_nodes: bool
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "WorkflowPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        runtime = runtime if isinstance(runtime, dict) else {}
        raw = runtime.get("workflow_canary")
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).casefold(),
            allocation_basis_points=max(0, min(_int(raw.get("allocation_basis_points"), 0), 10_000)),
            salt=str(raw.get("salt") or WORKFLOW_POLICY_VERSION),
            # Danh sách rỗng = fail-closed, y hệt các phase trước.
            allowed_slugs=tuple(str(x).strip() for x in (raw.get("allowed_slugs") or []) if str(x).strip()),
            max_nodes=max(1, min(_int(raw.get("max_nodes"), 24), workflow_graph.MAX_NODES)),
            max_parallel=max(1, min(_int(raw.get("max_parallel"), 3), workflow_graph.MAX_PARALLEL_WIDTH)),
            node_timeout_seconds=max(5.0, min(float(_int(raw.get("node_timeout_seconds"), 300)), 1800.0)),
            max_nesting_depth=max(0, min(_int(raw.get("max_nesting_depth"), 1),
                                         workflow_graph.MAX_NESTING_DEPTH)),
            # Node ghi trong workflow LUÔN phải hỏi người dùng. Cờ này chỉ quyết định
            # workflow có node ghi thì được chạy tới chỗ hỏi, hay bị chặn từ đầu.
            allow_write_nodes=bool(raw.get("allow_write_nodes", False)),
            version=str(raw.get("policy_version") or WORKFLOW_POLICY_VERSION)[:120],
        )

    def admits(self, slug: str, session_id: str) -> tuple[bool, int, str]:
        from fast_path_runtime import stable_bucket
        bucket = stable_bucket(session_id, self.salt)
        if self.mode not in ("canary", "on"):
            return False, bucket, "mode_not_canary"
        if bucket >= self.allocation_basis_points:
            return False, bucket, "outside_allocation"
        if slug not in self.allowed_slugs:
            return False, bucket, "workflow_not_allowlisted"
        return True, bucket, "admitted"


@dataclass(frozen=True)
class WorkflowAdmission:
    action: str
    reason: str
    graph: WorkflowGraph | None = None
    bucket: Optional[int] = None
    policy_version: str = WORKFLOW_POLICY_VERSION
    message: str = ""


@dataclass
class WorkflowRunResult:
    status: str
    output: str = ""
    stop_reason: str = ""
    task_id: str = ""
    completed_nodes: tuple[str, ...] = ()
    reused_nodes: tuple[str, ...] = ()
    pending_node_id: str = ""
    events: list[dict] = field(default_factory=list)


class WorkflowCanary:
    """Chạy một `WorkflowGraph`, checkpoint sau từng node, resume không chạy lại."""

    def __init__(self, runtime: context_runtime.ObserveRuntime,
                 settings_reader: Callable[[], dict],
                 graph_loader: GraphLoader | None = None,
                 state_encryptor: Callable[[str], str] | None = None,
                 state_decryptor: Callable[[str], str] | None = None):
        self.runtime = runtime
        self.settings_reader = settings_reader
        self.graph_loader = graph_loader
        self.state_encryptor = state_encryptor or secrets_store.encrypt_required
        self.state_decryptor = state_decryptor or secrets_store.decrypt

    def policy(self) -> WorkflowPolicy:
        try:
            return WorkflowPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            return WorkflowPolicy.from_settings({})

    # ------------------------------------------------------------------ admission

    def prepare(self, trace, graph: WorkflowGraph, session_id: str) -> WorkflowAdmission:
        policy = self.policy()
        if not trace:
            return WorkflowAdmission("legacy", "trace_unavailable", policy_version=policy.version)
        admitted, bucket, reason = policy.admits(graph.slug, session_id)
        if not admitted:
            return WorkflowAdmission("legacy", reason, bucket=bucket, policy_version=policy.version)
        if len(graph.nodes) > policy.max_nodes:
            return WorkflowAdmission("legacy", "graph_too_large", bucket=bucket,
                                     policy_version=policy.version)
        if graph.write_node_ids and not policy.allow_write_nodes:
            return WorkflowAdmission("legacy", "write_nodes_not_enabled", bucket=bucket,
                                     policy_version=policy.version)
        path = self.runtime.pin_execution_path(
            trace, "workflow", bucket, policy.version, "workflow_admission")
        if path != "workflow":
            return WorkflowAdmission("legacy", "task_already_pinned", bucket=bucket,
                                     policy_version=policy.version)
        return WorkflowAdmission("execute", "admitted", graph, bucket, policy.version)

    # ------------------------------------------------------------------ state

    def _initial_state(self, graph: WorkflowGraph, input_text: str, session_id: str,
                       depth: int = 0) -> dict:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "policy_version": self.policy().version,
            "workflow_slug": graph.slug,
            "workflow_revision": graph.revision,
            "graph_version": graph.graph_version,
            "adapter": graph.adapter,
            "session_id": str(session_id or ""),
            "input": str(input_text or ""),
            "depth": int(depth),
            "status": "RUNNING",
            "nodes": {x.id: {"status": "PENDING", "output": "", "attempts": 0,
                             "verified": None, "error": ""} for x in graph.nodes},
            "pending_node_id": "",
            "pending_code": "",
            "approved_nodes": [],
            "output": "",
            "stop_reason": "",
            "created_at": 0.0,
        }

    def _checkpoint(self, trace, state: dict, initialize: bool = False) -> bool:
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            encrypted = self.state_encryptor(payload)
        except Exception:
            return False
        digest = _sha(state)
        if initialize:
            try:
                objective = self.state_encryptor(
                    f"workflow:{state['workflow_slug']}@{state['workflow_revision']}")
            except Exception:
                return False
            return self.runtime.initialize_orchestrator(
                trace, _sha(state["session_id"]), objective, encrypted, digest,
                state["status"], {"kind": "workflow"}, None)
        return self.runtime.checkpoint_orchestrator(trace, encrypted, digest, state["status"])

    def load_state(self, task_id: str) -> dict | None:
        snapshot = self.runtime.load_orchestrator_checkpoint(task_id)
        if not snapshot or not snapshot.get("checkpoint"):
            return None
        try:
            state = json.loads(self.state_decryptor(snapshot["checkpoint"]["state_encrypted"]))
        except Exception:
            return None
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            return None
        return state

    # ------------------------------------------------------------------ execution

    @staticmethod
    def _interpolate(node: WorkflowNode, state: dict, graph: WorkflowGraph) -> str:
        """Giữ đúng ngữ nghĩa cũ: `{{input}}` và `{{prev}}` là thay chuỗi, không hơn."""
        previous = ""
        if node.depends_on:
            # Runner cũ chỉ thấy output của bước LIỀN TRƯỚC. Với đồ thị, "liền trước"
            # là dependency khai đầu tiên - trùng khớp với chuỗi thẳng của adapter cũ.
            previous = str((state["nodes"].get(node.depends_on[0]) or {}).get("output") or "")
        return node.task.replace("{{input}}", state.get("input") or "").replace(
            "{{prev}}", previous)

    async def _run_node(self, node: WorkflowNode, state: dict, graph: WorkflowGraph,
                        executor: NodeExecutor, policy: WorkflowPolicy,
                        capability_runner: CapabilityRunner | None = None) -> dict:
        prompt = self._interpolate(node, state, graph)
        approved = node.id in set(state.get("approved_nodes") or [])
        try:
            if node.kind == "capability":
                if capability_runner is None:
                    return {"status": "FAILED", "output": "",
                            "error": "capability_runner_not_available"}
                result = await asyncio.wait_for(
                    capability_runner(node, approved), timeout=policy.node_timeout_seconds)
            else:
                result = await asyncio.wait_for(
                    executor(node, prompt), timeout=policy.node_timeout_seconds)
        except asyncio.TimeoutError:
            return {"status": "FAILED", "output": "", "error": "node_timeout"}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {"status": "FAILED", "output": "", "error": f"node_error:{type(exc).__name__}"}
        result = result if isinstance(result, dict) else {}
        return {
            "status": "COMPLETED" if not result.get("error") else "FAILED",
            "output": str(result.get("output") or ""),
            "verified": result.get("verified"),
            "attempts": _int(result.get("attempts"), 1),
            "error": str(result.get("error") or ""),
        }

    async def run(self, trace, graph: WorkflowGraph, input_text: str, session_id: str,
                  executor: NodeExecutor, emit: Callable[[dict], Awaitable[None]] | None = None,
                  resume_state: dict | None = None, depth: int = 0,
                  capability_runner: CapabilityRunner | None = None) -> WorkflowRunResult:
        policy = self.policy()
        events: list[dict] = []

        async def _emit(event: dict) -> None:
            events.append(event)
            if emit is not None:
                await emit(event)

        state = resume_state or self._initial_state(graph, input_text, session_id, depth)
        reused: list[str] = []
        if resume_state is not None:
            # Ghim lại: revision đổi giữa chừng thì KHÔNG resume, vì node đã xong
            # không còn tương ứng với đồ thị hiện tại.
            if state.get("workflow_revision") != graph.revision:
                return WorkflowRunResult("FAILED", stop_reason="workflow_revision_mismatch",
                                         task_id=getattr(trace, "task_id", ""))
            reused = [nid for nid, item in state["nodes"].items()
                      if item.get("status") == "COMPLETED"]
            await _emit({"type": "resume", "reused": len(reused),
                         "workflow": graph.name})
        else:
            state["created_at"] = time.time()
            if not self._checkpoint(trace, state, initialize=True):
                return WorkflowRunResult("FAILED", stop_reason="checkpoint_unavailable",
                                         task_id=getattr(trace, "task_id", ""))
            await _emit({"type": "start", "workflow": graph.name, "steps": len(graph.nodes)})

        completed: list[str] = []
        for layer in graph.execution_layers():
            runnable = []
            for node_id in layer:
                node = graph.node(node_id)
                entry = state["nodes"].get(node_id) or {}
                if entry.get("status") == "COMPLETED":
                    continue  # BẤT BIẾN 1: node đã xong không bao giờ chạy lại.
                if any((state["nodes"].get(dep) or {}).get("status") != "COMPLETED"
                       for dep in node.depends_on):
                    state["nodes"][node_id] = {**entry, "status": "SKIPPED",
                                               "error": "dependency_failed"}
                    continue
                runnable.append(node)

            # BẤT BIẾN 2: gặp node ghi là dừng và hỏi, không tự chạy.
            approved_nodes = set(state.get("approved_nodes") or [])
            for node in runnable:
                if node.id in approved_nodes:
                    continue          # đã duyệt rồi thì không hỏi lại
                if node.is_write or node.kind == "wait_user":
                    state["pending_node_id"] = node.id
                    state["status"] = "WAITING_USER"
                    state["stop_reason"] = ("write_node_needs_confirmation"
                                            if node.is_write else "wait_user_node")
                    # Mã suy ra từ task + node + arguments, KHÔNG phải số ngẫu nhiên:
                    # sau restart vẫn tính lại được đúng mã cho đúng ý định, và một
                    # cú duyệt không dùng lại được cho node khác.
                    state["pending_code"] = _pending_code(
                        getattr(trace, "task_id", ""), node)
                    self._checkpoint(trace, state)
                    await _emit({"type": "wait_user", "node": node.id,
                                 "reason": state["stop_reason"],
                                 "code": state["pending_code"],
                                 "task_id": getattr(trace, "task_id", ""),
                                 "prompt": node.prompt or node.task})
                    return WorkflowRunResult(
                        "WAITING_USER", state.get("output") or "", state["stop_reason"],
                        getattr(trace, "task_id", ""), tuple(completed), tuple(reused),
                        node.id, events)

            if not runnable:
                continue

            for node in runnable:
                if node.kind == "workflow_call":
                    if depth >= policy.max_nesting_depth:
                        state["nodes"][node.id] = {"status": "FAILED", "output": "",
                                                   "error": "nesting_depth_exceeded",
                                                   "attempts": 0, "verified": None}
                        continue
                    child = self.graph_loader(node.workflow_slug) if self.graph_loader else None
                    if child is None or child.revision != node.workflow_revision:
                        state["nodes"][node.id] = {"status": "FAILED", "output": "",
                                                   "error": "nested_revision_mismatch",
                                                   "attempts": 0, "verified": None}
                        continue

            batch = [x for x in runnable if x.kind != "workflow_call"
                     or state["nodes"].get(x.id, {}).get("status") != "FAILED"]
            for index in range(0, len(batch), policy.max_parallel):
                chunk = batch[index:index + policy.max_parallel]
                for node in chunk:
                    await _emit({"type": "step_start", "i": node.metadata.get("legacy_index", 0),
                                 "node": node.id, "agent": node.agent,
                                 "task": self._interpolate(node, state, graph)})
                results = await asyncio.gather(*[
                    self._run_node(node, state, graph, executor, policy, capability_runner)
                    for node in chunk
                ], return_exceptions=True)
                for node, result in zip(chunk, results):
                    if isinstance(result, BaseException):
                        result = {"status": "FAILED", "output": "",
                                  "error": f"node_error:{type(result).__name__}"}
                    state["nodes"][node.id] = {
                        "status": result["status"], "output": result.get("output") or "",
                        "attempts": _int(result.get("attempts"), 1),
                        "verified": result.get("verified"), "error": result.get("error") or "",
                    }
                    if result["status"] == "COMPLETED":
                        completed.append(node.id)
                    await _emit({"type": "step_done",
                                 "i": node.metadata.get("legacy_index", 0),
                                 "node": node.id, "agent": node.agent,
                                 "output": result.get("output") or "",
                                 "verified": result.get("verified")})
                # Checkpoint sau MỖI lô, trước khi chạy lô kế: tiến trình chết ở đây
                # thì resume không mất phần đã xong.
                if not self._checkpoint(trace, state):
                    # Checkpoint hỏng thường là do OCC: một tiến trình khác đã resume
                    # đúng task này. Đi tiếp là hai bên cùng chạy một node - dừng ngay.
                    await _emit({"type": "error", "content": "checkpoint_failed"})
                    return WorkflowRunResult(
                        "FAILED", state.get("output") or "", "checkpoint_failed",
                        getattr(trace, "task_id", ""), tuple(completed), tuple(reused),
                        "", events)

        output_entry = state["nodes"].get(graph.output_node_id) or {}
        failed = [nid for nid, item in state["nodes"].items() if item.get("status") == "FAILED"]
        state["output"] = str(output_entry.get("output") or "")
        state["status"] = "FAILED" if failed else "COMPLETED"
        state["stop_reason"] = "node_failed" if failed else "objective_satisfied"
        state["pending_node_id"] = ""
        self._checkpoint(trace, state)
        await _emit({"type": "done", "result": state["output"]})
        return WorkflowRunResult(
            state["status"], state["output"], state["stop_reason"],
            getattr(trace, "task_id", ""), tuple(completed), tuple(reused), "", events)

    async def resume(self, trace, task_id: str, graph: WorkflowGraph, executor: NodeExecutor,
                     emit: Callable[[dict], Awaitable[None]] | None = None,
                     confirmed_node_id: str = "", confirmation_code: str = "",
                     capability_runner: CapabilityRunner | None = None) -> WorkflowRunResult:
        """Chạy tiếp từ checkpoint. Node đã COMPLETED giữ nguyên, không gọi lại executor."""
        state = self.load_state(task_id)
        if state is None:
            return WorkflowRunResult("FAILED", stop_reason="workflow_state_unavailable",
                                     task_id=task_id)
        pending = state.get("pending_node_id") or ""
        if pending:
            expected = str(state.get("pending_code") or "")
            # Mã sai thì đứng yên y như node sai. Duyệt phải gắn với ĐÚNG ý định này.
            if expected and str(confirmation_code or "").strip().upper() != expected:
                return WorkflowRunResult("WAITING_USER", state.get("output") or "",
                                         "confirmation_code_mismatch", task_id,
                                         pending_node_id=pending)
            if confirmed_node_id != pending:
                # Không có xác nhận đúng node thì vẫn đứng yên, không tự đi tiếp.
                return WorkflowRunResult("WAITING_USER", state.get("output") or "",
                                         state.get("stop_reason") or "wait_user_node",
                                         task_id, pending_node_id=pending)
            node = graph.node(pending)
            if node is not None and node.kind == "wait_user":
                state["nodes"][pending] = {
                    "status": "COMPLETED", "output": state.get("input") or "",
                    "attempts": 1, "verified": True, "error": "",
                }
            state["pending_node_id"] = ""
            state["pending_code"] = ""
            state["status"] = "RUNNING"
            # Node ghi ĐÃ được duyệt: ghi vào state để vòng chạy tới không dừng lại lần
            # nữa. Danh sách này là bằng chứng duyệt, nên nó đi cùng checkpoint.
            approved = list(state.get("approved_nodes") or [])
            if pending not in approved:
                approved.append(pending)
            state["approved_nodes"] = approved
        return await self.run(trace, graph, state.get("input") or "",
                              state.get("session_id") or "", executor, emit,
                              resume_state=state, depth=_int(state.get("depth"), 0),
                              capability_runner=capability_runner)
