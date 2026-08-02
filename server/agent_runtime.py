"""Adaptive Runtime Phase 11: agent = workflow CÓ QUYỀN tự lập lại kế hoạch.

Phase 10 cho workflow một đồ thị cố định. Phase 11 cho phép sau khi chạy xong mà
Quality Gate chưa hài lòng thì agent được đề xuất thêm node và chạy tiếp - trong
đúng ngân sách và đúng quyền đã cấp từ đầu.

Bất biến quan trọng nhất của phase này, và cũng là thứ dễ hỏng nhất:

    **Replan KHÔNG BAO GIỜ được cấp thêm quyền.**

Tập capability được ghim lúc khởi tạo. Node do model đề xuất chỉ được dùng lại đúng
những gì đã có trong tập đó. Model không thể mở rộng quyền của chính nó bằng cách
đề xuất một kế hoạch mới - đó là lý do việc kiểm tra nằm ở đây, trong code, chứ
không nằm trong prompt.

Ba đường dừng, không có đường thứ tư: đạt mục tiêu, hết ngân sách, hoặc lặp lại
cùng một dấu vết lỗi. Trường hợp cuối được escalate ra người dùng thay vì thử mãi.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import workflow_graph
from workflow_graph import WorkflowGraph, WorkflowNode
from workflow_runtime import WorkflowCanary, WorkflowRunResult

AGENT_POLICY_VERSION = "agent-replan-canary-v1"

# Người lập kế hoạch bổ sung: nhận (objective, tóm tắt state, tập quyền đã cấp)
# và trả danh sách node đề xuất. Trả rỗng nghĩa là "không biết làm gì thêm".
Planner = Callable[[str, dict, dict], Awaitable[list[dict]]]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8", errors="replace")).hexdigest()


# Runtime báo dừng vì lý do KHÔNG phải "kết quả chưa đạt". Replan trong các trường
# hợp này là sai bản chất, nên agent dừng luôn.
_RUNTIME_TERMINAL_REASONS = frozenset({
    "checkpoint_failed", "workflow_revision_mismatch", "checkpoint_unavailable",
    "workflow_state_unavailable",
})


class PermissionEscalation(PermissionError):
    """Kế hoạch mới đòi quyền chưa được cấp. Luôn dừng, không bao giờ nới ra."""


@dataclass(frozen=True)
class AgentPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    allowed_slugs: tuple[str, ...]
    max_replan_rounds: int
    max_total_nodes: int
    max_nodes_per_replan: int
    failure_repeat_limit: int
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "AgentPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        runtime = runtime if isinstance(runtime, dict) else {}
        raw = runtime.get("agent_canary")
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).casefold(),
            allocation_basis_points=max(0, min(_int(raw.get("allocation_basis_points"), 0), 10_000)),
            salt=str(raw.get("salt") or AGENT_POLICY_VERSION),
            allowed_slugs=tuple(str(x).strip() for x in (raw.get("allowed_slugs") or []) if str(x).strip()),
            max_replan_rounds=max(0, min(_int(raw.get("max_replan_rounds"), 2), 8)),
            max_total_nodes=max(1, min(_int(raw.get("max_total_nodes"), 24),
                                       workflow_graph.MAX_NODES)),
            max_nodes_per_replan=max(1, min(_int(raw.get("max_nodes_per_replan"), 3), 8)),
            failure_repeat_limit=max(1, min(_int(raw.get("failure_repeat_limit"), 2), 5)),
            version=str(raw.get("policy_version") or AGENT_POLICY_VERSION)[:120],
        )

    def admits(self, slug: str, session_id: str) -> tuple[bool, int, str]:
        from fast_path_runtime import stable_bucket
        bucket = stable_bucket(session_id, self.salt)
        if self.mode not in ("canary", "on"):
            return False, bucket, "mode_not_canary"
        if bucket >= self.allocation_basis_points:
            return False, bucket, "outside_allocation"
        if slug not in self.allowed_slugs:
            return False, bucket, "agent_not_allowlisted"
        return True, bucket, "admitted"


@dataclass(frozen=True)
class CapabilityGrant:
    """Quyền ghim lúc khởi tạo. Chỉ để đọc; không có đường nào nới nó ra."""
    agent_slugs: frozenset[str]
    capability_names: frozenset[str]
    capability_ids: frozenset[str]
    allows_write: bool
    allows_nested_workflow: bool

    @classmethod
    def from_graph(cls, graph: WorkflowGraph) -> "CapabilityGrant":
        return cls(
            agent_slugs=frozenset(x.agent for x in graph.nodes if x.agent),
            capability_names=frozenset(x.capability_name for x in graph.nodes if x.capability_name),
            capability_ids=frozenset(x.capability_id for x in graph.nodes if x.capability_id),
            allows_write=bool(graph.write_node_ids),
            allows_nested_workflow=any(x.kind == "workflow_call" for x in graph.nodes),
        )

    def check(self, node: WorkflowNode) -> str:
        """Trả mã lỗi nếu node vượt quyền; chuỗi rỗng nếu hợp lệ."""
        if node.kind not in ("model_step", "capability"):
            # workflow_call/compensation/wait_user do người viết workflow khai, không
            # phải thứ model được tự thêm vào giữa chừng.
            return f"replan_node_kind_not_allowed:{node.kind}"
        if node.kind == "model_step":
            if node.agent not in self.agent_slugs:
                return f"replan_agent_not_granted:{node.agent[:40]}"
            if node.verify_agent and node.verify_agent not in self.agent_slugs:
                return f"replan_verify_agent_not_granted:{node.verify_agent[:40]}"
            return ""
        if node.effect == "write" and not self.allows_write:
            return "replan_write_not_granted"
        if node.capability_id and node.capability_id not in self.capability_ids:
            return f"replan_capability_id_not_granted:{node.capability_id[:40]}"
        if node.capability_name and node.capability_name not in self.capability_names:
            return f"replan_capability_not_granted:{node.capability_name[:40]}"
        return ""


@dataclass
class AgentRunResult:
    status: str
    output: str = ""
    stop_reason: str = ""
    task_id: str = ""
    replan_rounds: int = 0
    added_node_ids: tuple[str, ...] = ()
    escalation: str = ""
    events: list[dict] = field(default_factory=list)
    # Output đến từ node nào. Cần thiết vì khi node output cuối hỏng, ta trả kết quả
    # của node hoàn tất gần nhất - người dùng phải biết mình đang đọc cái gì.
    output_node_id: str = ""


class AgentRunner:
    """Chạy một workflow, rồi cho phép nó lập thêm kế hoạch trong đúng quyền đã cấp."""

    def __init__(self, canary: WorkflowCanary, settings_reader: Callable[[], dict],
                 quality_gate=None):
        self.canary = canary
        self.settings_reader = settings_reader
        self.quality_gate = quality_gate

    def policy(self) -> AgentPolicy:
        try:
            return AgentPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            return AgentPolicy.from_settings({})

    @staticmethod
    def _best_output(state: dict, preferred_node_id: str) -> tuple[str, str]:
        """Node output ưu tiên; nếu nó rỗng thì lấy node hoàn tất GẦN NHẤT.

        Vòng replan hỏng không được xoá sạch công sức các vòng trước: trả rỗng trong
        khi đã có kết quả tốt là tệ hơn hẳn việc trả kết quả cũ kèm nói rõ nguồn.
        """
        nodes = state.get("nodes") or {}
        preferred = (nodes.get(preferred_node_id) or {}).get("output") or ""
        if preferred:
            return preferred, preferred_node_id
        for node_id, item in reversed(list(nodes.items())):
            if (item or {}).get("status") == "COMPLETED" and (item or {}).get("output"):
                return item["output"], node_id
        return "", ""

    @staticmethod
    def _failure_signature(state: dict) -> str:
        """Dấu vết lỗi của một vòng: node nào hỏng vì lý do gì, không kèm nội dung."""
        failures = sorted(
            (nid, str((item or {}).get("error") or ""))
            for nid, item in (state.get("nodes") or {}).items()
            if (item or {}).get("status") == "FAILED"
        )
        return _sha(failures) if failures else ""

    def _validated_nodes(self, proposed: list[dict], grant: CapabilityGrant,
                         existing_ids: set[str], round_index: int,
                         policy: AgentPolicy) -> list[WorkflowNode]:
        """Biến đề xuất của model thành node, từ chối mọi thứ vượt quyền đã cấp."""
        if len(proposed) > policy.max_nodes_per_replan:
            raise PermissionEscalation("replan_too_many_nodes")
        out: list[WorkflowNode] = []
        for index, item in enumerate(proposed or []):
            if not isinstance(item, dict):
                raise PermissionEscalation("replan_node_not_mapping")
            node_id = f"r{round_index}_{index}"
            depends = [str(x) for x in (item.get("depends_on") or []) if str(x)]
            # Chỉ được phụ thuộc vào node ĐÃ TỒN TẠI, để chu trình là bất khả thi.
            for dep in depends:
                if dep not in existing_ids:
                    raise PermissionEscalation(f"replan_unknown_dependency:{dep[:40]}")
            node = WorkflowNode(
                id=node_id,
                kind=str(item.get("kind") or "model_step"),
                depends_on=tuple(depends),
                agent=str(item.get("agent") or "").strip(),
                task=str(item.get("task") or ""),
                verify_agent=str(item.get("verify_agent") or "").strip(),
                max_retries=max(0, _int(item.get("max_retries", 1), 0)),
                capability_id=str(item.get("capability_id") or "").strip(),
                capability_name=str(item.get("capability") or item.get("capability_name") or "").strip(),
                effect=str(item.get("effect") or "none").strip(),
                metadata={"replan_round": round_index},
            )
            error = grant.check(node)
            if error:
                # Đây là ranh giới an toàn: model đòi quyền chưa cấp thì DỪNG cả vòng,
                # không lặng lẽ bỏ node đó rồi chạy phần còn lại.
                raise PermissionEscalation(error)
            out.append(node)
            existing_ids.add(node_id)
        return out

    @staticmethod
    def _extend(graph: WorkflowGraph, new_nodes: list[WorkflowNode],
                output_node_id: str) -> WorkflowGraph:
        nodes = tuple(graph.nodes) + tuple(new_nodes)
        payload = {"base": graph.revision,
                   "added": [{"id": x.id, "kind": x.kind, "agent": x.agent,
                              "task": x.task, "capability_name": x.capability_name,
                              "capability_id": x.capability_id, "effect": x.effect,
                              "depends_on": list(x.depends_on)} for x in new_nodes]}
        return WorkflowGraph(
            slug=graph.slug, name=graph.name, description=graph.description,
            status=graph.status, nodes=nodes,
            input_contract=graph.input_contract, output_contract=graph.output_contract,
            output_node_id=output_node_id, revision=_sha(payload),
            source_hash=graph.source_hash, adapter=graph.adapter,
            resumable=graph.resumable, max_risk=graph.max_risk,
            compensation=graph.compensation,
        )

    async def run(self, trace, graph: WorkflowGraph, input_text: str, session_id: str,
                  executor, planner: Planner,
                  emit: Callable[[dict], Awaitable[None]] | None = None,
                  capability_runner=None) -> AgentRunResult:
        policy = self.policy()
        grant = CapabilityGrant.from_graph(graph)
        events: list[dict] = []

        async def _emit(event: dict) -> None:
            events.append(event)
            if emit is not None:
                await emit(event)

        current = graph
        state = None
        seen_signatures: dict[str, int] = {}
        added: list[str] = []
        rounds = 0
        result: WorkflowRunResult | None = None

        while True:
            result = await self.canary.run(
                trace, current, input_text, session_id, executor, _emit,
                resume_state=state, capability_runner=capability_runner)
            # `_emit` đã gom event vào `events` rồi; đừng gộp thêm result.events, vì
            # phép loại trùng theo GIÁ TRỊ sẽ nuốt mất event lặp lại một cách hợp lệ.
            state = self.canary.load_state(result.task_id) if result.task_id else None
            if result.status == "WAITING_USER":
                return AgentRunResult(result.status, result.output, result.stop_reason,
                                      result.task_id, rounds, tuple(added), "", events)
            if result.stop_reason in _RUNTIME_TERMINAL_REASONS:
                # Đây không phải "chưa đạt mục tiêu" mà là runtime nói dừng: checkpoint
                # hỏng nghĩa là tiến trình khác đang giữ task, revision lệch nghĩa là
                # định nghĩa đã đổi. Replan lúc này là chạy đè lên người khác.
                text, from_node = self._best_output(state or {}, current.output_node_id)
                return AgentRunResult("STOPPED", text, result.stop_reason,
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)
            if state is None:
                return AgentRunResult("FAILED", result.output, "agent_state_unavailable",
                                      result.task_id, rounds, tuple(added), "", events)

            decision = self._evaluate(result, state)
            if decision == "pass":
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("COMPLETED", text, "objective_satisfied",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)

            signature = self._failure_signature(state)
            if signature:
                seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
                if seen_signatures[signature] >= policy.failure_repeat_limit:
                    # Lặp lại cùng một lỗi thì thử nữa cũng vô ích. Đưa ra người dùng.
                    await _emit({"type": "escalation", "reason": "repeated_failure_signature"})
                    text, from_node = self._best_output(state, current.output_node_id)
                    return AgentRunResult(
                        "ESCALATED", text, "repeated_failure_signature",
                        result.task_id, rounds, tuple(added),
                        "Agent gặp lại đúng một lỗi nhiều lần nên dừng để anh xem.",
                        events, from_node)

            if rounds >= policy.max_replan_rounds:
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("STOPPED", text, "replan_budget_exhausted",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)
            if len(current.nodes) >= policy.max_total_nodes:
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("STOPPED", text, "node_budget_exhausted",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)

            summary = {
                "objective": input_text,
                "nodes": {nid: {"status": item.get("status"), "error": item.get("error")}
                          for nid, item in (state.get("nodes") or {}).items()},
                "decision": decision,
            }
            granted = {
                "agents": sorted(grant.agent_slugs),
                "capabilities": sorted(grant.capability_names),
                "allows_write": grant.allows_write,
            }
            try:
                proposed = await planner(input_text, summary, granted)
            except Exception as exc:
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("STOPPED", text,
                                      f"planner_error:{type(exc).__name__}",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)
            if not proposed:
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("STOPPED", text, "planner_had_nothing_to_add",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)

            rounds += 1
            existing = {x.id for x in current.nodes}
            try:
                new_nodes = self._validated_nodes(
                    list(proposed), grant, existing, rounds, policy)
            except PermissionEscalation as exc:
                await _emit({"type": "escalation", "reason": str(exc)})
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult(
                    "ESCALATED", text, str(exc), result.task_id,
                    rounds, tuple(added),
                    "Kế hoạch mới đòi quyền chưa được cấp nên Javis đã dừng.",
                    events, from_node)
            if len(current.nodes) + len(new_nodes) > policy.max_total_nodes:
                text, from_node = self._best_output(state, current.output_node_id)
                return AgentRunResult("STOPPED", text, "node_budget_exhausted",
                                      result.task_id, rounds, tuple(added), "", events,
                                      from_node)

            added.extend(x.id for x in new_nodes)
            current = self._extend(current, new_nodes, new_nodes[-1].id)
            # Chuyển revision một cách TƯỜNG MINH: đây là replan có kiểm soát, khác hẳn
            # việc định nghĩa workflow bị sửa ngoài ý muốn (trường hợp đó vẫn bị chặn).
            state["workflow_revision"] = current.revision
            for node in new_nodes:
                state["nodes"][node.id] = {"status": "PENDING", "output": "",
                                           "attempts": 0, "verified": None, "error": ""}
            state["status"] = "RUNNING"
            await _emit({"type": "replan", "round": rounds,
                         "added": [x.id for x in new_nodes]})

    def _evaluate(self, result: WorkflowRunResult, state: dict) -> str:
        """Quality Gate quyết định đã đủ chưa. Không có gate thì dựa vào trạng thái node."""
        if result.status != "COMPLETED":
            return "gather_more"
        if self.quality_gate is None:
            return "pass"
        try:
            decision = self.quality_gate.evaluate(
                state.get("input") or "", result.output or "", "workflow")
        except Exception:
            return "pass"
        return "pass" if decision.status == "pass" else decision.status
