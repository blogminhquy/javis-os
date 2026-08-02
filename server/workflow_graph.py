"""Adaptive Runtime Phase 10: workflow như capability graph.

Tầng này THUẦN DỮ LIỆU: không I/O, không gọi model, không đụng SQLite. Nó chỉ biến
định nghĩa workflow thành một đồ thị đã kiểm tra hợp lệ, kèm hợp đồng input/output
và revision content-addressed. Nhờ vậy validation chạy được trong test mà không cần
dựng nguyên hệ.

Hai nguồn đồ thị:

- `compile_legacy_workflow`: adapter cho định dạng ĐANG DÙNG (`steps[]` với đúng bốn
  trường agent/task/verify_agent/max_retries). Workflow cũ không có hợp đồng dữ liệu
  nào cả, nên adapter phải TỰ SUY RA chứ không đọc được từ file. Suy ra theo hướng
  giữ nguyên hành vi: một chuỗi vào, chuỗi của bước cuối đi ra.
- `compile_native_workflow`: định dạng mới có `nodes[]`, cho phép depends_on, điều
  kiện, nhánh song song, chờ người dùng và gọi workflow con theo revision.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

WORKFLOW_GRAPH_VERSION = "workflow-graph-v1"
LEGACY_ADAPTER_VERSION = "legacy-linear-v1"
NATIVE_ADAPTER_VERSION = "native-dag-v1"

# Trần an toàn của policy, không phải thuật toán chọn. Vượt trần là từ chối biên dịch
# chứ không cắt bớt im lặng.
MAX_NODES = 64
MAX_NESTING_DEPTH = 3
MAX_PARALLEL_WIDTH = 8

NODE_KINDS = frozenset({
    "model_step", "capability", "condition", "wait_user", "workflow_call", "compensation",
})
# Phase 10 không mở effect `dangerous` trong bất kỳ cấu hình nào, y như Phase 9.
ALLOWED_EFFECTS = frozenset({"none", "read", "write"})

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_NODE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class WorkflowContractError(ValueError):
    """Định nghĩa workflow không hợp lệ. Luôn fail-closed, không tự chữa."""


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8", errors="replace")).hexdigest()


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    kind: str
    depends_on: tuple[str, ...] = ()
    # model_step
    agent: str = ""
    task: str = ""
    verify_agent: str = ""
    max_retries: int = 1
    # capability
    capability_id: str = ""
    capability_name: str = ""
    effect: str = "none"
    arguments: dict = field(default_factory=dict)
    # workflow_call
    workflow_slug: str = ""
    workflow_revision: str = ""
    # condition
    when: dict = field(default_factory=dict)
    # compensation
    compensates: str = ""
    # wait_user
    prompt: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def is_write(self) -> bool:
        return self.kind == "capability" and self.effect == "write"


@dataclass(frozen=True)
class WorkflowGraph:
    """`allows_replan` là ranh giới giữa Phase 10 và 11: workflow thường có đồ thị cố
    định, agent được đề xuất thêm node sau khi chạy - nhưng chỉ trong quyền đã cấp."""
    slug: str
    name: str
    description: str
    status: str
    nodes: tuple[WorkflowNode, ...]
    input_contract: dict
    output_contract: dict
    output_node_id: str
    revision: str
    source_hash: str
    adapter: str
    resumable: bool
    max_risk: str
    compensation: dict
    allows_replan: bool = False
    graph_version: str = WORKFLOW_GRAPH_VERSION

    def node(self, node_id: str) -> WorkflowNode | None:
        for item in self.nodes:
            if item.id == node_id:
                return item
        return None

    @property
    def write_node_ids(self) -> tuple[str, ...]:
        return tuple(x.id for x in self.nodes if x.is_write)

    @property
    def nested_slugs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            x.workflow_slug for x in self.nodes if x.kind == "workflow_call" and x.workflow_slug
        ))

    def execution_layers(self) -> tuple[tuple[str, ...], ...]:
        """Chia node thành các lớp chạy được song song, tôn trọng depends_on."""
        remaining = {x.id: set(x.depends_on) for x in self.nodes}
        done: set[str] = set()
        layers: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(sorted(k for k, deps in remaining.items() if deps <= done))
            if not ready:  # pragma: no cover - validate_graph đã chặn chu trình
                raise WorkflowContractError("workflow_graph_cycle")
            layers.append(ready)
            for key in ready:
                remaining.pop(key, None)
            done.update(ready)
        return tuple(layers)


def _validate_nodes(nodes: list[WorkflowNode]) -> None:
    if not nodes:
        raise WorkflowContractError("workflow_has_no_nodes")
    if len(nodes) > MAX_NODES:
        raise WorkflowContractError("workflow_too_many_nodes")
    seen: set[str] = set()
    for node in nodes:
        if not _NODE_ID_RE.match(node.id):
            raise WorkflowContractError(f"invalid_node_id:{node.id[:40]}")
        if node.id in seen:
            raise WorkflowContractError(f"duplicate_node_id:{node.id[:40]}")
        if node.kind not in NODE_KINDS:
            raise WorkflowContractError(f"unknown_node_kind:{node.kind[:40]}")
        # depends_on chỉ được trỏ về node ĐÃ khai trước đó. Luật này khiến chu trình
        # là bất khả thi ngay từ cấu trúc, mà vẫn diễn tả được mọi DAG (mọi DAG đều
        # có ít nhất một thứ tự topo).
        for dep in node.depends_on:
            if dep not in seen:
                raise WorkflowContractError(f"unknown_or_forward_dependency:{dep[:40]}")
        if node.kind == "model_step" and not node.agent:
            raise WorkflowContractError(f"model_step_without_agent:{node.id}")
        if node.kind == "capability":
            if node.effect not in ALLOWED_EFFECTS:
                raise WorkflowContractError(f"effect_not_allowed:{node.effect[:40]}")
            if not node.capability_id and not node.capability_name:
                raise WorkflowContractError(f"capability_node_without_target:{node.id}")
        if node.kind == "workflow_call":
            if not _SLUG_RE.match(node.workflow_slug or ""):
                raise WorkflowContractError(f"invalid_nested_slug:{node.id}")
            # Ghim revision là BẮT BUỘC: workflow con đổi giữa chừng mà cha không biết
            # thì lineage vô nghĩa và resume không tái lập được.
            if not node.workflow_revision:
                raise WorkflowContractError(f"nested_workflow_without_revision:{node.id}")
        if node.kind == "compensation":
            if node.compensates not in seen:
                raise WorkflowContractError(f"compensation_for_unknown_node:{node.id}")
        seen.add(node.id)
    widest = max(len(layer) for layer in _layers_of(nodes))
    if widest > MAX_PARALLEL_WIDTH:
        raise WorkflowContractError("workflow_parallel_width_exceeded")


def _layers_of(nodes: list[WorkflowNode]) -> list[tuple[str, ...]]:
    remaining = {x.id: set(x.depends_on) for x in nodes}
    done: set[str] = set()
    layers: list[tuple[str, ...]] = []
    while remaining:
        ready = tuple(sorted(k for k, deps in remaining.items() if deps <= done))
        if not ready:
            raise WorkflowContractError("workflow_graph_cycle")
        layers.append(ready)
        for key in ready:
            remaining.pop(key, None)
        done.update(ready)
    return layers


def _risk_of(nodes: list[WorkflowNode]) -> str:
    if any(x.is_write for x in nodes):
        return "write"
    if any(x.kind == "capability" and x.effect == "read" for x in nodes):
        return "read"
    return "none"


def compile_legacy_workflow(meta: dict, slug: str) -> WorkflowGraph:
    """Bọc định dạng workflow đang dùng vào đồ thị, GIỮ NGUYÊN hành vi.

    Workflow cũ chạy tuần tự, truyền dữ liệu bằng thay chuỗi `{{prev}}`, và chỉ output
    của bước cuối là quan sát được. Adapter giữ đúng cả ba điểm đó: node xếp thành một
    chuỗi thẳng, cạnh dữ liệu vẫn là chuỗi, `output_node_id` là node cuối.
    """
    meta = meta if isinstance(meta, dict) else {}
    steps = meta.get("steps")
    steps = steps if isinstance(steps, list) else []
    nodes: list[WorkflowNode] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise WorkflowContractError(f"legacy_step_not_mapping:{index}")
        agent = str(step.get("agent") or "").strip()
        if not agent:
            raise WorkflowContractError(f"legacy_step_without_agent:{index}")
        nodes.append(WorkflowNode(
            id=f"s{index}",
            kind="model_step",
            depends_on=(f"s{index - 1}",) if index else (),
            agent=agent,
            task=str(step.get("task") or ""),
            verify_agent=str(step.get("verify_agent") or "").strip(),
            # Giữ nguyên phép quy đổi của runner cũ: thiếu/0/không parse được -> 0.
            max_retries=max(0, _int(step.get("max_retries", 1), 0)),
            metadata={"legacy_index": index},
        ))
    _validate_nodes(nodes)
    payload = {
        "slug": slug,
        "adapter": LEGACY_ADAPTER_VERSION,
        "graph_version": WORKFLOW_GRAPH_VERSION,
        "steps": [{
            "id": x.id, "agent": x.agent, "task": x.task,
            "verify_agent": x.verify_agent, "max_retries": x.max_retries,
        } for x in nodes],
    }
    return WorkflowGraph(
        slug=slug,
        name=str(meta.get("name") or slug),
        description=str(meta.get("description") or ""),
        status=str(meta.get("status") or "active"),
        nodes=tuple(nodes),
        # Hợp đồng SUY RA, không đọc được từ file: workflow cũ không khai gì cả.
        input_contract={
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
            "derived": True,
        },
        output_contract={
            "type": "object",
            "properties": {"output": {"type": "string"}},
            "required": ["output"],
            "additionalProperties": False,
            "derived": True,
            "note": "Chỉ output của node cuối, đúng như runner cũ.",
        },
        output_node_id=nodes[-1].id,
        revision=_sha(payload),
        source_hash=_sha(meta),
        adapter=LEGACY_ADAPTER_VERSION,
        # Workflow cũ toàn model step nên chạy lại một node là an toàn.
        resumable=True,
        max_risk=_risk_of(nodes),
        compensation={},
       allows_replan=bool(meta.get("agent") or meta.get("allows_replan")),
    )


def compile_native_workflow(meta: dict, slug: str) -> WorkflowGraph:
    """Định dạng mới: `nodes[]` khai tường minh depends_on, effect và workflow con."""
    meta = meta if isinstance(meta, dict) else {}
    raw_nodes = meta.get("nodes")
    raw_nodes = raw_nodes if isinstance(raw_nodes, list) else []
    nodes: list[WorkflowNode] = []
    for index, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            raise WorkflowContractError(f"node_not_mapping:{index}")
        depends = item.get("depends_on") or []
        depends = depends if isinstance(depends, list) else [depends]
        nodes.append(WorkflowNode(
            id=str(item.get("id") or f"n{index}"),
            kind=str(item.get("kind") or "model_step"),
            depends_on=tuple(str(x) for x in depends if str(x)),
            agent=str(item.get("agent") or "").strip(),
            task=str(item.get("task") or ""),
            verify_agent=str(item.get("verify_agent") or "").strip(),
            max_retries=max(0, _int(item.get("max_retries", 1), 0)),
            capability_id=str(item.get("capability_id") or "").strip(),
            capability_name=str(item.get("capability") or item.get("capability_name") or "").strip(),
            effect=str(item.get("effect") or "none").strip(),
            arguments=item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
            workflow_slug=str(item.get("workflow") or item.get("workflow_slug") or "").strip(),
            workflow_revision=str(item.get("workflow_revision") or "").strip(),
            when=item.get("when") if isinstance(item.get("when"), dict) else {},
            compensates=str(item.get("compensates") or "").strip(),
            prompt=str(item.get("prompt") or ""),
            metadata={"declared_index": index},
        ))
    _validate_nodes(nodes)
    output_node = str(meta.get("output_node") or (nodes[-1].id if nodes else ""))
    if not any(x.id == output_node for x in nodes):
        raise WorkflowContractError(f"unknown_output_node:{output_node[:40]}")
    declared_input = meta.get("input_contract")
    declared_output = meta.get("output_contract")
    payload = {
        "slug": slug, "adapter": NATIVE_ADAPTER_VERSION,
        "graph_version": WORKFLOW_GRAPH_VERSION,
        "output_node": output_node,
        "nodes": [{
            "id": x.id, "kind": x.kind, "depends_on": list(x.depends_on),
            "agent": x.agent, "task": x.task, "verify_agent": x.verify_agent,
            "max_retries": x.max_retries, "capability_id": x.capability_id,
            "capability_name": x.capability_name, "effect": x.effect,
            "arguments": x.arguments, "workflow_slug": x.workflow_slug,
            "workflow_revision": x.workflow_revision, "when": x.when,
            "compensates": x.compensates, "prompt": x.prompt,
        } for x in nodes],
        "input_contract": declared_input, "output_contract": declared_output,
    }
    compensation = {x.compensates: x.id for x in nodes if x.kind == "compensation"}
    return WorkflowGraph(
        slug=slug,
        name=str(meta.get("name") or slug),
        description=str(meta.get("description") or ""),
        status=str(meta.get("status") or "active"),
        nodes=tuple(nodes),
        input_contract=declared_input if isinstance(declared_input, dict) else {
            "type": "object", "properties": {"input": {"type": "string"}},
            "required": [], "additionalProperties": False, "derived": True,
        },
        output_contract=declared_output if isinstance(declared_output, dict) else {
            "type": "object", "properties": {"output": {"type": "string"}},
            "required": ["output"], "additionalProperties": False, "derived": True,
        },
        output_node_id=output_node,
        revision=_sha(payload),
        source_hash=_sha(meta),
        adapter=NATIVE_ADAPTER_VERSION,
        # Có node write mà không khai được đường bù thì KHÔNG tự nhận là resume được:
        # resume một workflow từng ghi ra ngoài là quyết định phải có bằng chứng.
        resumable=all(x.id in compensation for x in nodes if x.is_write) or not any(
            x.is_write for x in nodes),
        max_risk=_risk_of(nodes),
        compensation=compensation,
       allows_replan=bool(meta.get("agent") or meta.get("allows_replan")),
    )


def compile_workflow(meta: dict, slug: str) -> WorkflowGraph:
    """Chọn adapter theo định dạng file, không cần người dùng khai."""
    if not _SLUG_RE.match(str(slug or "")):
        raise WorkflowContractError(f"invalid_workflow_slug:{str(slug)[:40]}")
    if isinstance((meta or {}).get("nodes"), list):
        return compile_native_workflow(meta, slug)
    return compile_legacy_workflow(meta, slug)


def manifest_of(graph: WorkflowGraph, relative_path: str = "") -> dict:
    """Manifest cho Registry: metadata + hợp đồng, KHÔNG kèm thân prompt của node."""
    return {
        "slug": graph.slug,
        "name": graph.name,
        "description": graph.description,
        "status": graph.status,
        "revision": graph.revision,
        "source_hash": graph.source_hash,
        "adapter": graph.adapter,
        "graph_version": graph.graph_version,
        "node_count": len(graph.nodes),
        "node_kinds": sorted({x.kind for x in graph.nodes}),
        "max_risk": graph.max_risk,
        "resumable": graph.resumable,
        "has_write_node": bool(graph.write_node_ids),
        "nested_slugs": list(graph.nested_slugs),
        "input_contract": graph.input_contract,
        "output_contract": graph.output_contract,
        "relative_path": str(relative_path or "")[:500],
    }
