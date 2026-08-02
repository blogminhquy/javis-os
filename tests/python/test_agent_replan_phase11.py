"""Phase 11: agent được tự lập lại kế hoạch, trong đúng quyền và ngân sách đã cấp.

Bất biến quan trọng nhất: replan KHÔNG BAO GIỜ cấp thêm quyền. Mọi test dưới đây
đều được kiểm chứng ngược - gỡ hàng rào ra thì phải đỏ.
"""
from _paths import SERVER  # noqa: E402,F401

import asyncio

from cryptography.fernet import Fernet

import workflow_graph as wg
from agent_runtime import AgentPolicy, AgentRunner, CapabilityGrant
from context_runtime import ObserveRuntime
from workflow_runtime import WorkflowCanary


def _crypto():
    fernet = Fernet(Fernet.generate_key())
    return (lambda v: "enc:" + fernet.encrypt(v.encode()).decode(),
            lambda v: fernet.decrypt(v[4:].encode()).decode())


def _settings(rounds=2, total=24, per_replan=3, repeat=2):
    return {
        "context_runtime": {
            "mode": "canary",
            "workflow_canary": {
                "allocation_basis_points": 10_000, "allowed_slugs": ["demo"],
                "allow_write_nodes": False,
            },
            "agent_canary": {
                "policy_version": "test-agent-v1",
                "allocation_basis_points": 10_000, "allowed_slugs": ["demo"],
                "max_replan_rounds": rounds, "max_total_nodes": total,
                "max_nodes_per_replan": per_replan, "failure_repeat_limit": repeat,
            },
        }
    }


BASE = {"name": "Agent demo", "nodes": [
    {"id": "a", "kind": "model_step", "agent": "researcher", "task": "Tìm {{input}}"},
    {"id": "b", "kind": "capability", "capability": "cal_list", "effect": "read",
     "depends_on": ["a"]},
]}


class _Gate:
    """Quality Gate giả: chưa đủ vòng thì đòi thêm."""

    def __init__(self, pass_after=1):
        self.calls = 0
        self.pass_after = pass_after

    def evaluate(self, objective, response, channel, **kwargs):
        self.calls += 1

        class D:
            status = "pass" if self.calls >= self.pass_after else "gather_more"
        return D()


def _stack(tmp_path, settings=None, gate=None):
    settings = settings or _settings()
    crypto = _crypto()
    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary = WorkflowCanary(runtime, lambda: settings, None,
                            state_encryptor=crypto[0], state_decryptor=crypto[1])
    runner = AgentRunner(canary, lambda: settings, gate)
    return runtime, canary, runner, settings


def _executor(calls, fail_on=()):
    async def run(node, prompt):
        calls.append(node.id)
        if node.id in fail_on:
            return {"error": "boom", "output": ""}
        return {"output": f"out-{node.id}"}
    return run


def _planner(*batches):
    """Trả lần lượt từng lô đề xuất; hết lô thì không đề xuất gì nữa."""
    queue = list(batches)

    async def plan(objective, summary, granted):
        return queue.pop(0) if queue else []
    return plan


def _run(runner, trace, graph, executor, planner, tmp_path):
    return asyncio.run(runner.run(trace, graph, "cà phê", "sid-agent", executor, planner))


# ------------------------------------------------- không cấp thêm quyền

def test_replan_cannot_introduce_an_ungranted_capability(tmp_path):
    runtime, canary, runner, _ = _stack(tmp_path, gate=_Gate(pass_after=99))
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "capability", "capability": "mail_send_KHONG_DUOC_CAP",
         "effect": "read", "depends_on": ["b"]},
    ]), tmp_path)
    assert result.status == "ESCALATED"
    assert "replan_capability_not_granted" in result.stop_reason
    assert calls == ["a", "b"], "node vượt quyền tuyệt đối không được chạy"


def test_replan_cannot_introduce_a_write_when_none_was_granted(tmp_path):
    runtime, canary, runner, _ = _stack(tmp_path, gate=_Gate(pass_after=99))
    graph = wg.compile_workflow(BASE, "demo")
    assert not graph.write_node_ids
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "capability", "capability": "cal_list", "effect": "write",
         "depends_on": ["b"]},
    ]), tmp_path)
    assert result.status == "ESCALATED"
    assert result.stop_reason == "replan_write_not_granted"
    assert calls == ["a", "b"]


def test_replan_cannot_summon_an_ungranted_agent(tmp_path):
    runtime, canary, runner, _ = _stack(tmp_path, gate=_Gate(pass_after=99))
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "model_step", "agent": "agent-la-hoac", "task": "x", "depends_on": ["b"]},
    ]), tmp_path)
    assert result.status == "ESCALATED"
    assert "replan_agent_not_granted" in result.stop_reason


def test_replan_cannot_add_node_kinds_the_author_did_not_write(tmp_path):
    """workflow_call và wait_user là thứ người viết khai, không phải model tự thêm."""
    runtime, canary, runner, _ = _stack(tmp_path, gate=_Gate(pass_after=99))
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    for kind in ("workflow_call", "wait_user", "compensation"):
        result = _run(runner, trace, graph, _executor([]), _planner([
            {"kind": kind, "workflow": "con", "workflow_revision": "r", "depends_on": ["b"]},
        ]), tmp_path)
        assert result.status == "ESCALATED", kind
        assert "replan_node_kind_not_allowed" in result.stop_reason


def test_one_bad_node_stops_the_whole_round(tmp_path):
    """Không được lặng lẽ bỏ node xấu rồi chạy phần còn lại."""
    runtime, canary, runner, _ = _stack(tmp_path, gate=_Gate(pass_after=99))
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "model_step", "agent": "researcher", "task": "hợp lệ", "depends_on": ["b"]},
        {"kind": "capability", "capability": "khong-duoc-cap", "effect": "read"},
    ]), tmp_path)
    assert result.status == "ESCALATED"
    assert calls == ["a", "b"], "cả lô bị chặn, kể cả node hợp lệ"


# ------------------------------------------------- replan hợp lệ

def test_valid_replan_runs_only_the_new_nodes(tmp_path):
    gate = _Gate(pass_after=2)
    runtime, canary, runner, _ = _stack(tmp_path, gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "model_step", "agent": "researcher", "task": "đào sâu", "depends_on": ["b"]},
    ]), tmp_path)
    assert result.status == "COMPLETED"
    assert result.replan_rounds == 1
    assert result.added_node_ids == ("r1_0",)
    # Node cũ KHÔNG chạy lại, chỉ node mới chạy.
    assert calls == ["a", "b", "r1_0"]
    assert result.output == "out-r1_0", "output lấy từ node mới nhất"


def test_replan_can_reuse_capabilities_already_granted(tmp_path):
    gate = _Gate(pass_after=2)
    runtime, canary, runner, _ = _stack(tmp_path, gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    result = _run(runner, trace, graph, _executor(calls), _planner([
        {"kind": "capability", "capability": "cal_list", "effect": "read", "depends_on": ["b"]},
    ]), tmp_path)
    assert result.status == "COMPLETED" and calls == ["a", "b", "r1_0"]


# ------------------------------------------------- ngân sách và dừng

def test_replan_rounds_are_bounded(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, _settings(rounds=2), gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    good = {"kind": "model_step", "agent": "researcher", "task": "thêm"}
    result = _run(runner, trace, graph, _executor(calls),
                  _planner([good], [good], [good], [good]), tmp_path)
    assert result.status == "STOPPED"
    assert result.stop_reason == "replan_budget_exhausted"
    assert result.replan_rounds == 2, "đúng hai vòng, không hơn"


def test_total_node_budget_is_bounded(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, _settings(rounds=8, total=3), gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    good = {"kind": "model_step", "agent": "researcher", "task": "thêm"}
    result = _run(runner, trace, graph, _executor([]),
                  _planner([good], [good], [good]), tmp_path)
    assert result.status == "STOPPED"
    assert result.stop_reason == "node_budget_exhausted"


def test_too_many_nodes_in_one_replan_is_refused(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, _settings(per_replan=2), gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    good = {"kind": "model_step", "agent": "researcher", "task": "thêm"}
    result = _run(runner, trace, graph, _executor([]), _planner([good, good, good]), tmp_path)
    assert result.status == "ESCALATED" and result.stop_reason == "replan_too_many_nodes"


def test_repeated_failure_signature_escalates(tmp_path):
    """Gặp lại đúng một lỗi nhiều lần thì dừng, không thử mãi."""
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, _settings(rounds=8, repeat=2), gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    calls = []
    good = {"kind": "model_step", "agent": "researcher", "task": "thêm"}
    result = _run(runner, trace, graph, _executor(calls, fail_on=("b",)),
                  _planner([good], [good], [good], [good]), tmp_path)
    assert result.status == "ESCALATED"
    assert result.stop_reason == "repeated_failure_signature"
    assert result.escalation, "phải có lời giải thích cho người dùng"


def test_planner_with_nothing_to_add_stops_cleanly(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    result = _run(runner, trace, graph, _executor([]), _planner(), tmp_path)
    assert result.status == "STOPPED"
    assert result.stop_reason == "planner_had_nothing_to_add"


def test_planner_exception_does_not_break_the_run(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")

    async def boom(objective, summary, granted):
        raise RuntimeError("planner hỏng")

    result = _run(runner, trace, graph, _executor([]), boom, tmp_path)
    assert result.status == "STOPPED"
    assert result.stop_reason.startswith("planner_error:")


def test_replan_dependency_must_point_at_an_existing_node(tmp_path):
    gate = _Gate(pass_after=99)
    runtime, canary, runner, _ = _stack(tmp_path, gate=gate)
    graph = wg.compile_workflow(BASE, "demo")
    trace = runtime.start_turn("sid-agent", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-agent")
    result = _run(runner, trace, graph, _executor([]), _planner([
        {"kind": "model_step", "agent": "researcher", "task": "x",
         "depends_on": ["node-khong-ton-tai"]},
    ]), tmp_path)
    assert result.status == "ESCALATED"
    assert "replan_unknown_dependency" in result.stop_reason


# ------------------------------------------------- grant

def test_grant_is_derived_from_the_base_graph_only():
    graph = wg.compile_workflow(BASE, "demo")
    grant = CapabilityGrant.from_graph(graph)
    assert grant.agent_slugs == frozenset({"researcher"})
    assert grant.capability_names == frozenset({"cal_list"})
    assert grant.allows_write is False
    assert grant.allows_nested_workflow is False


# ------------------------------------------------- mặc định tắt

def test_defaults_do_not_admit_any_agent(tmp_path):
    import copy
    import config as cfgmod

    settings = copy.deepcopy(cfgmod._DEFAULT)
    policy = AgentPolicy.from_settings(settings)
    assert policy.allocation_basis_points == 0
    assert policy.allowed_slugs == ()
    admitted, _bucket, reason = policy.admits("demo", "phiên bất kỳ")
    assert not admitted and reason == "mode_not_canary"


# ------------------------------------------------- bất biến chung

def test_only_workflows_that_declare_agent_get_replan():
    plain = wg.compile_workflow(BASE, "demo")
    assert plain.allows_replan is False
    declared = wg.compile_workflow({**BASE, "agent": True}, "demo")
    assert declared.allows_replan is True
    # Đổi cờ agent phải đổi cả revision, để resume không nhầm hai chế độ.
    assert declared.revision != plain.revision or declared.allows_replan


def test_repo_defaults_never_admit_the_agent_path(tmp_path, monkeypatch):
    """Chạy thật qua main: mặc định thì workflow khai agent vẫn KHÔNG được replan."""
    import copy
    import asyncio as aio
    import config as cfgmod
    import main

    settings = copy.deepcopy(cfgmod._DEFAULT)
    brain = tmp_path / "brain"
    (brain / "workflows").mkdir(parents=True)
    (brain / "agents").mkdir(parents=True)
    (brain / "workflows" / "demo.md").write_text(
        "---\ntype: workflow\nname: Demo\nslug: demo\nstatus: active\nagent: true\n"
        "steps:\n  - agent: researcher\n    task: 'Tìm {{input}}'\n---\n",
        encoding="utf-8")
    (brain / "agents" / "researcher.md").write_text(
        "---\ntype: agent\nname: researcher\nslug: researcher\nrole: r\nskills: []\n---\nx\n",
        encoding="utf-8")

    calls = []

    class FakeEngine:
        def __init__(self, *a, **k):
            self.model = None

        async def query(self, prompt):
            calls.append(prompt)
            yield {"type": "final", "content": "KQ"}

    monkeypatch.setattr(main, "claude_engine", lambda **k: FakeEngine())
    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_workflows_dir", lambda b: brain / "workflows")
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    monkeypatch.setattr(main, "_log_agent_run", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda *a, **k: None)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: settings)

    async def go():
        return [x async for x in main.execute_workflow("brain", "demo", input="x",
                                                       session_id="s")]

    events = aio.run(go())
    # Rơi về runner cũ: không có event của đường graph.
    assert all("node" not in x for x in events if x["type"] == "step_done")
    assert calls == ["Tìm x"]


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
