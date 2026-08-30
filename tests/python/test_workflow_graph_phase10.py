"""Phase 10: workflow như capability graph, có checkpoint và resume.

Trọng tâm là ba bất biến: workflow cũ chạy tương đương qua adapter, node đã xong
không chạy lại sau restart, và node ghi không bao giờ tự chạy.
"""
from _paths import SERVER  # noqa: E402,F401

import asyncio
import json

from cryptography.fernet import Fernet

import workflow_graph as wg
from context_runtime import ObserveRuntime
from workflow_runtime import WorkflowCanary, WorkflowPolicy


def _crypto():
    fernet = Fernet(Fernet.generate_key())
    return (lambda v: "enc:" + fernet.encrypt(v.encode()).decode(),
            lambda v: fernet.decrypt(v[4:].encode()).decode())


def _settings(allocation=10_000, slugs=("demo",), allow_write=False, parallel=3):
    return {
        "context_runtime": {
            "mode": "canary",
            "workflow_canary": {
                "policy_version": "test-workflow-v1",
                "allocation_basis_points": allocation,
                "allowed_slugs": list(slugs),
                "max_parallel": parallel,
                "allow_write_nodes": allow_write,
                "max_nesting_depth": 1,
            },
        }
    }


LEGACY = {
    "name": "Nghiên cứu rồi viết", "status": "active",
    "steps": [
        {"agent": "researcher", "task": "Tìm hiểu {{input}}"},
        {"agent": "writer", "task": "Viết bài từ: {{prev}}", "verify_agent": "editor",
         "max_retries": 2},
    ],
}


def _stack(tmp_path, settings=None, graph_loader=None):
    settings = settings or _settings()
    crypto = _crypto()
    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary = WorkflowCanary(runtime, lambda: settings, graph_loader,
                            state_encryptor=crypto[0], state_decryptor=crypto[1])
    return runtime, canary, settings, crypto


def _executor(calls, outputs=None, fail_on=()):
    async def run(node, prompt):
        calls.append({"node": node.id, "agent": node.agent, "prompt": prompt})
        if node.id in fail_on:
            return {"error": "boom", "output": ""}
        return {"output": (outputs or {}).get(node.id, f"out-{node.id}"), "verified": True}
    return run


# ----------------------------------------------------------------- adapter cũ

def test_legacy_adapter_preserves_shape_and_string_semantics():
    graph = wg.compile_workflow(LEGACY, "demo")
    assert graph.adapter == wg.LEGACY_ADAPTER_VERSION
    assert [x.id for x in graph.nodes] == ["s0", "s1"]
    # Chuỗi thẳng: mỗi bước phụ thuộc đúng bước trước.
    assert graph.nodes[0].depends_on == () and graph.nodes[1].depends_on == ("s0",)
    # Giữ nguyên bốn trường của định dạng cũ.
    assert graph.nodes[1].verify_agent == "editor" and graph.nodes[1].max_retries == 2
    # Output vẫn chỉ là bước cuối, đúng như runner cũ.
    assert graph.output_node_id == "s1"
    # Hợp đồng là SUY RA, không phải đọc được từ file.
    assert graph.input_contract["derived"] and graph.output_contract["derived"]
    assert graph.max_risk == "none" and graph.resumable


def test_revision_is_content_addressed_and_stable():
    first = wg.compile_workflow(LEGACY, "demo")
    assert wg.compile_workflow(LEGACY, "demo").revision == first.revision
    changed = json.loads(json.dumps(LEGACY))
    changed["steps"][0]["task"] = "Tìm hiểu kỹ hơn {{input}}"
    assert wg.compile_workflow(changed, "demo").revision != first.revision
    # Đổi thứ mô tả thuần tuý thì đồ thị không đổi.
    cosmetic = {**LEGACY, "description": "mô tả mới"}
    assert wg.compile_workflow(cosmetic, "demo").revision == first.revision


def test_interpolation_matches_legacy_runner(tmp_path):
    runtime, canary, settings, _ = _stack(tmp_path)
    graph = wg.compile_workflow(LEGACY, "demo")
    trace = runtime.start_turn("sid-wf", str(tmp_path), "dashboard")
    assert canary.prepare(trace, graph, "sid-wf").action == "execute"
    calls = []
    result = asyncio.run(canary.run(
        trace, graph, "thị trường cà phê", "sid-wf", _executor(calls)))
    assert result.status == "COMPLETED"
    # {{input}} vào bước đầu, {{prev}} là output bước trước - đúng ngữ nghĩa cũ.
    assert calls[0]["prompt"] == "Tìm hiểu thị trường cà phê"
    assert calls[1]["prompt"] == "Viết bài từ: out-s0"
    assert result.output == "out-s1"


# ----------------------------------------------------------------- DAG

def test_independent_nodes_run_in_one_layer(tmp_path):
    native = {"name": "song song", "nodes": [
        {"id": "a", "kind": "model_step", "agent": "x", "task": "A"},
        {"id": "b", "kind": "model_step", "agent": "y", "task": "B"},
        {"id": "c", "kind": "model_step", "agent": "z", "task": "C", "depends_on": ["a", "b"]},
    ]}
    graph = wg.compile_workflow(native, "demo")
    assert graph.execution_layers() == (("a", "b"), ("c",))

    runtime, canary, *_ = _stack(tmp_path)
    trace = runtime.start_turn("sid-par", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-par")
    active = {"now": 0, "max": 0}

    async def run(node, prompt):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.02)
        active["now"] -= 1
        return {"output": f"out-{node.id}"}

    result = asyncio.run(canary.run(trace, graph, "x", "sid-par", run))
    assert result.status == "COMPLETED" and active["max"] == 2


def test_failed_dependency_skips_dependents_without_running_them(tmp_path):
    native = {"name": "chuỗi", "nodes": [
        {"id": "a", "kind": "model_step", "agent": "x", "task": "A"},
        {"id": "b", "kind": "model_step", "agent": "y", "task": "B", "depends_on": ["a"]},
    ]}
    graph = wg.compile_workflow(native, "demo")
    runtime, canary, *_ = _stack(tmp_path)
    trace = runtime.start_turn("sid-fail", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-fail")
    calls = []
    result = asyncio.run(canary.run(
        trace, graph, "x", "sid-fail", _executor(calls, fail_on=("a",))))
    assert result.status == "FAILED"
    assert [x["node"] for x in calls] == ["a"], "node phụ thuộc không được chạy"


# ----------------------------------------------------------------- resume

def test_resume_does_not_rerun_completed_nodes(tmp_path):
    native = {"name": "ba bước", "nodes": [
        {"id": "a", "kind": "model_step", "agent": "x", "task": "A"},
        {"id": "b", "kind": "model_step", "agent": "y", "task": "B", "depends_on": ["a"]},
        {"id": "c", "kind": "model_step", "agent": "z", "task": "C", "depends_on": ["b"]},
    ]}
    graph = wg.compile_workflow(native, "demo")
    settings = _settings()
    crypto = _crypto()
    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary = WorkflowCanary(runtime, lambda: settings, None,
                            state_encryptor=crypto[0], state_decryptor=crypto[1])
    trace = runtime.start_turn("sid-res", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-res")

    first_calls = []

    async def crash_at_c(node, prompt):
        first_calls.append(node.id)
        if node.id == "c":
            raise RuntimeError("tiến trình chết")
        return {"output": f"out-{node.id}"}

    first = asyncio.run(canary.run(trace, graph, "x", "sid-res", crash_at_c))
    assert first.status == "FAILED" and first_calls == ["a", "b", "c"]
    task_id = trace.task_id
    runtime.close()

    # Tiến trình mới, cùng file DB.
    runtime2 = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary2 = WorkflowCanary(runtime2, lambda: settings, None,
                             state_encryptor=crypto[0], state_decryptor=crypto[1])
    trace2 = runtime2.resume_trace(task_id)
    second_calls = []
    second = asyncio.run(canary2.resume(
        trace2, task_id, graph, _executor(second_calls)))
    assert second.status == "COMPLETED"
    assert [x["node"] for x in second_calls] == ["c"], "chỉ node chưa xong mới chạy lại"
    assert set(second.reused_nodes) == {"a", "b"}
    # Output của node đã xong được lấy từ checkpoint, không phải chạy lại.
    assert second_calls[0]["prompt"] == "C"


def test_resume_refuses_when_workflow_definition_changed(tmp_path):
    graph = wg.compile_workflow(LEGACY, "demo")
    settings = _settings()
    crypto = _crypto()
    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary = WorkflowCanary(runtime, lambda: settings, None,
                            state_encryptor=crypto[0], state_decryptor=crypto[1])
    trace = runtime.start_turn("sid-chg", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-chg")
    asyncio.run(canary.run(trace, graph, "x", "sid-chg",
                           _executor([], fail_on=("s1",))))
    task_id = trace.task_id

    edited = json.loads(json.dumps(LEGACY))
    edited["steps"][1]["task"] = "Viết KHÁC HẲN từ {{prev}}"
    new_graph = wg.compile_workflow(edited, "demo")
    calls = []
    result = asyncio.run(canary.resume(
        runtime.resume_trace(task_id), task_id, new_graph, _executor(calls)))
    assert result.status == "FAILED"
    assert result.stop_reason == "workflow_revision_mismatch"
    assert not calls, "định nghĩa đã đổi thì không được chạy tiếp node nào"


# ----------------------------------------------------------------- node ghi

def test_write_node_pauses_and_never_runs_by_itself(tmp_path):
    native = {"name": "có ghi", "nodes": [
        {"id": "a", "kind": "model_step", "agent": "x", "task": "soạn"},
        {"id": "w", "kind": "capability", "capability": "mail_send", "effect": "write",
         "depends_on": ["a"]},
    ]}
    graph = wg.compile_workflow(native, "demo")
    assert graph.write_node_ids == ("w",) and graph.max_risk == "write"

    # Mặc định workflow có node ghi bị chặn từ cổng admission.
    runtime, canary, *_ = _stack(tmp_path)
    trace = runtime.start_turn("sid-w1", str(tmp_path), "dashboard")
    assert canary.prepare(trace, graph, "sid-w1").reason == "write_nodes_not_enabled"

    # Bật lên thì vẫn chỉ chạy tới node ghi rồi DỪNG hỏi, không tự gọi.
    runtime2, canary2, *_ = _stack(tmp_path / "b", _settings(allow_write=True))
    trace2 = runtime2.start_turn("sid-w2", str(tmp_path), "dashboard")
    assert canary2.prepare(trace2, graph, "sid-w2").action == "execute"
    calls = []
    result = asyncio.run(canary2.run(trace2, graph, "x", "sid-w2", _executor(calls)))
    assert result.status == "WAITING_USER"
    assert result.pending_node_id == "w"
    assert result.stop_reason == "write_node_needs_confirmation"
    assert [x["node"] for x in calls] == ["a"], "node ghi tuyệt đối không được gọi"


def test_pending_write_stays_put_without_matching_confirmation(tmp_path):
    native = {"name": "chờ", "nodes": [
        {"id": "q", "kind": "wait_user", "prompt": "Duyệt nhé?"},
        {"id": "b", "kind": "model_step", "agent": "y", "task": "tiếp", "depends_on": ["q"]},
    ]}
    graph = wg.compile_workflow(native, "demo")
    runtime, canary, settings, crypto = _stack(tmp_path)
    trace = runtime.start_turn("sid-wait", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-wait")
    first = asyncio.run(canary.run(trace, graph, "x", "sid-wait", _executor([])))
    assert first.status == "WAITING_USER" and first.pending_node_id == "q"
    code = [e for e in first.events if e["type"] == "wait_user"][0]["code"]
    assert code and len(code) == 6
    task_id = trace.task_id

    calls = []
    # Sai node thì đứng yên.
    stuck = asyncio.run(canary.resume(
        runtime.resume_trace(task_id), task_id, graph, _executor(calls),
        confirmed_node_id="sai-node", confirmation_code=code))
    assert stuck.status == "WAITING_USER" and not calls

    # Đúng node nhưng SAI MÃ cũng đứng yên - duyệt phải gắn với đúng ý định.
    wrong_code = asyncio.run(canary.resume(
        runtime.resume_trace(task_id), task_id, graph, _executor(calls),
        confirmed_node_id="q", confirmation_code="XXXXXX"))
    assert wrong_code.status == "WAITING_USER"
    assert wrong_code.stop_reason == "confirmation_code_mismatch"
    assert not calls

    went = asyncio.run(canary.resume(
        runtime.resume_trace(task_id), task_id, graph, _executor(calls),
        confirmed_node_id="q", confirmation_code=code))
    assert went.status == "COMPLETED"
    assert [x["node"] for x in calls] == ["b"]


# ----------------------------------------------------------------- workflow con

def test_nested_workflow_requires_pinned_revision(tmp_path):
    child_meta = {"name": "con", "steps": [{"agent": "a", "task": "làm"}]}
    child = wg.compile_workflow(child_meta, "con")
    parent = {"name": "cha", "nodes": [
        {"id": "n", "kind": "workflow_call", "workflow": "con",
         "workflow_revision": child.revision},
    ]}
    graph = wg.compile_workflow(parent, "demo")
    assert graph.nested_slugs == ("con",)

    # Workflow con bị sửa -> revision lệch -> node hỏng, không chạy nhầm bản mới.
    edited = {**child_meta, "steps": [{"agent": "a", "task": "làm khác"}]}
    stale = wg.compile_workflow(edited, "con")
    runtime, canary, *_ = _stack(tmp_path, graph_loader=lambda slug: stale)
    trace = runtime.start_turn("sid-n", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-n")
    result = asyncio.run(canary.run(trace, graph, "x", "sid-n", _executor([])))
    assert result.status == "FAILED"


def test_graph_validation_rejects_every_malformed_shape():
    """Từng luật một, có case riêng - để gỡ luật nào ra là đỏ luật đó."""
    cases = {
        "nested_workflow_without_revision": {"nodes": [
            {"id": "n", "kind": "workflow_call", "workflow": "con"}]},
        "effect_not_allowed": {"nodes": [
            {"id": "n", "kind": "capability", "capability": "rm", "effect": "dangerous"}]},
        "duplicate_node_id": {"nodes": [
            {"id": "a", "kind": "model_step", "agent": "x"},
            {"id": "a", "kind": "model_step", "agent": "y"}]},
        "unknown_or_forward_dependency": {"nodes": [
            {"id": "a", "kind": "model_step", "agent": "x", "depends_on": ["b"]},
            {"id": "b", "kind": "model_step", "agent": "y"}]},
        "unknown_node_kind": {"nodes": [{"id": "a", "kind": "bịa ra"}]},
        "model_step_without_agent": {"nodes": [
            {"id": "a", "kind": "model_step", "task": "x"}]},
        "capability_node_without_target": {"nodes": [
            {"id": "a", "kind": "capability", "effect": "read"}]},
        "compensation_for_unknown_node": {"nodes": [
            {"id": "c", "kind": "compensation", "compensates": "không có"}]},
        "workflow_has_no_nodes": {"nodes": []},
        "invalid_node_id": {"nodes": [{"id": "id có dấu cách", "kind": "model_step",
                                       "agent": "x"}]},
    }
    for expected, meta in cases.items():
        try:
            wg.compile_workflow(meta, "demo")
        except wg.WorkflowContractError as exc:
            assert expected in str(exc), (expected, str(exc))
        else:
            raise AssertionError(f"phải từ chối: {expected}")

    # Slug workflow cũng phải hợp lệ.
    try:
        wg.compile_workflow(LEGACY, "Slug Sai")
    except wg.WorkflowContractError as exc:
        assert "invalid_workflow_slug" in str(exc)
    else:
        raise AssertionError("slug sai phải bị từ chối")

    # Bước cũ thiếu agent cũng không được lọt qua adapter.
    try:
        wg.compile_workflow({"steps": [{"task": "không có agent"}]}, "demo")
    except wg.WorkflowContractError as exc:
        assert "legacy_step_without_agent" in str(exc)
    else:
        raise AssertionError("bước cũ thiếu agent phải bị từ chối")


# ----------------------------------------------------------------- mặc định tắt

def test_defaults_do_not_admit_any_workflow(tmp_path):
    import copy
    import config as cfgmod

    settings = copy.deepcopy(cfgmod._DEFAULT)
    policy = WorkflowPolicy.from_settings(settings)
    assert policy.allocation_basis_points == 0
    assert policy.allowed_slugs == ()
    assert policy.allow_write_nodes is False
    admitted, _bucket, reason = policy.admits("demo", "bất kỳ session nào")
    assert not admitted and reason == "mode_not_canary"

    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    canary = WorkflowCanary(runtime, lambda: settings)
    trace = runtime.start_turn("sid-def", str(tmp_path), "dashboard")
    graph = wg.compile_workflow(LEGACY, "demo")
    assert canary.prepare(trace, graph, "sid-def").action == "legacy"


def test_a_write_node_runs_only_after_the_right_code_is_confirmed(tmp_path):
    """Duyệt đúng mã thì node ghi CHẠY. Sai mã, sai node, hay chưa duyệt thì tuyệt đối không."""
    native = {"name": "có ghi", "nodes": [
        {"id": "a", "kind": "model_step", "agent": "x", "task": "soạn"},
        {"id": "w", "kind": "capability", "capability": "mail_send", "effect": "write",
         "depends_on": ["a"], "arguments": {"to": "khach@vidu.com"}},
    ]}
    graph = wg.compile_workflow(native, "demo")
    runtime, canary, *_ = _stack(tmp_path, _settings(allow_write=True))
    trace = runtime.start_turn("sid-wc", str(tmp_path), "dashboard")
    canary.prepare(trace, graph, "sid-wc")

    written = []

    async def capability_runner(node, approved):
        assert approved, "chỉ được gọi sau khi đã duyệt"
        written.append(node.id)
        return {"output": "đã gửi"}

    first = asyncio.run(canary.run(trace, graph, "x", "sid-wc", _executor([]),
                                   capability_runner=capability_runner))
    assert first.status == "WAITING_USER" and first.pending_node_id == "w"
    assert not written, "chưa duyệt thì tuyệt đối không chạy"
    code = [e for e in first.events if e["type"] == "wait_user"][0]["code"]

    # Sai mã: vẫn không chạy.
    wrong = asyncio.run(canary.resume(
        runtime.resume_trace(trace.task_id), trace.task_id, graph, _executor([]),
        confirmed_node_id="w", confirmation_code="XXXXXX",
        capability_runner=capability_runner))
    assert wrong.stop_reason == "confirmation_code_mismatch" and not written

    # Đúng mã: chạy đúng một lần.
    ok = asyncio.run(canary.resume(
        runtime.resume_trace(trace.task_id), trace.task_id, graph, _executor([]),
        confirmed_node_id="w", confirmation_code=code,
        capability_runner=capability_runner))
    assert ok.status == "COMPLETED"
    assert written == ["w"]


def test_the_confirmation_code_is_derived_not_random(tmp_path):
    """Mã suy ra từ task + node + arguments nên restart vẫn tính lại được đúng mã,
    và mã của node này không dùng được cho node khác."""
    from workflow_runtime import _pending_code

    node_a = wg.compile_workflow({"name": "x", "nodes": [
        {"id": "w", "kind": "capability", "capability": "mail_send", "effect": "write",
         "arguments": {"to": "a@b.c"}}]}, "demo").nodes[0]
    node_b = wg.compile_workflow({"name": "x", "nodes": [
        {"id": "w", "kind": "capability", "capability": "mail_send", "effect": "write",
         "arguments": {"to": "KHAC@b.c"}}]}, "demo").nodes[0]

    assert _pending_code("task-1", node_a) == _pending_code("task-1", node_a)
    assert _pending_code("task-1", node_a) != _pending_code("task-2", node_a)
    assert _pending_code("task-1", node_a) != _pending_code("task-1", node_b), (
        "đổi tham số phải đổi mã, nếu không mã cũ duyệt được việc mới")



# ------------------------------------------- tích hợp qua main.execute_workflow

def _brain_with_workflow(tmp_path, monkeypatch, settings):
    """Dựng một brain thật có workflow + agent để chạy qua đúng main.execute_workflow."""
    import main

    brain = tmp_path / "brain"
    (brain / "workflows").mkdir(parents=True)
    (brain / "agents").mkdir(parents=True)
    (brain / "workflows" / "demo.md").write_text(
        "---\n"
        "type: workflow\nname: Demo\nslug: demo\nstatus: active\n"
        "steps:\n"
        "  - agent: researcher\n    task: 'Tìm {{input}}'\n"
        "  - agent: writer\n    task: 'Viết từ {{prev}}'\n"
        "---\n", encoding="utf-8")
    for slug in ("researcher", "writer"):
        (brain / "agents" / f"{slug}.md").write_text(
            f"---\ntype: agent\nname: {slug}\nslug: {slug}\nrole: r\nskills: []\n---\nthân\n",
            encoding="utf-8")

    calls = []

    class FakeEngine:
        def __init__(self, *a, **k):
            self.model = None

        async def query(self, prompt):
            calls.append(prompt)
            yield {"type": "final", "content": f"KQ({len(calls)})"}

    monkeypatch.setattr(main, "claude_engine", lambda **k: FakeEngine())
    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_workflows_dir", lambda b: brain / "workflows")
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    monkeypatch.setattr(main, "_log_agent_run", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda *a, **k: None)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: settings)
    return main, brain, calls


def _drain(gen):
    async def go():
        return [x async for x in gen]
    return asyncio.run(go())


def test_graph_path_and_legacy_runner_agree(tmp_path, monkeypatch):
    """Bất biến của spec: workflow hiện tại chạy TƯƠNG ĐƯƠNG qua adapter."""
    import copy
    import config as cfgmod

    # Đường cũ: mặc định repo (allocation 0).
    off = copy.deepcopy(cfgmod._DEFAULT)
    main, brain, legacy_calls = _brain_with_workflow(tmp_path / "a", monkeypatch, off)
    legacy_events = _drain(main.execute_workflow("brain", "demo", input="cà phê"))
    legacy_result = [x for x in legacy_events if x["type"] == "done"][0]["result"]

    # Đường mới: bật canary cho đúng slug này.
    on = copy.deepcopy(cfgmod._DEFAULT)
    on["context_runtime"]["mode"] = "canary"
    on["context_runtime"]["workflow_canary"].update(
        {"allocation_basis_points": 10_000, "allowed_slugs": ["demo"]})
    main2, brain2, graph_calls = _brain_with_workflow(tmp_path / "b", monkeypatch, on)
    graph_events = _drain(
        main2.execute_workflow("brain", "demo", input="cà phê", session_id="s1"))
    graph_result = [x for x in graph_events if x["type"] == "done"][0]["result"]

    # Cùng prompt gửi cho agent, cùng kết quả cuối.
    assert legacy_calls == graph_calls == ["Tìm cà phê", "Viết từ KQ(1)"]
    assert legacy_result == graph_result == "KQ(2)"
    # Đường mới vẫn phát bộ event dashboard đang nghe.
    assert {"start", "step_start", "step_done", "done"} <= {x["type"] for x in graph_events}


def test_repo_defaults_keep_workflows_on_the_legacy_runner(tmp_path, monkeypatch):
    import copy
    import config as cfgmod

    settings = copy.deepcopy(cfgmod._DEFAULT)
    main, brain, calls = _brain_with_workflow(tmp_path, monkeypatch, settings)
    events = _drain(main.execute_workflow("brain", "demo", input="x", session_id="s"))
    assert [x["type"] for x in events][0] == "start"
    # Đường graph gắn thêm "node" vào step_done; runner cũ thì không.
    assert all("node" not in x for x in events if x["type"] == "step_done")
    assert calls == ["Tìm x", "Viết từ KQ(1)"]


def test_graph_failure_falls_back_to_legacy_runner(tmp_path, monkeypatch):
    """Lỗi ở đường mới không được cướp lượt chạy của người dùng."""
    import copy
    import config as cfgmod

    on = copy.deepcopy(cfgmod._DEFAULT)
    on["context_runtime"]["mode"] = "canary"
    on["context_runtime"]["workflow_canary"].update(
        {"allocation_basis_points": 10_000, "allowed_slugs": ["demo"]})
    main, brain, calls = _brain_with_workflow(tmp_path, monkeypatch, on)

    def boom(*a, **k):
        raise RuntimeError("đường graph hỏng")

    monkeypatch.setattr(main, "execute_workflow_graph", boom)
    events = _drain(main.execute_workflow("brain", "demo", input="x", session_id="s"))
    assert [x for x in events if x["type"] == "done"][0]["result"] == "KQ(2)"
    assert calls == ["Tìm x", "Viết từ KQ(1)"]


def test_workflow_source_exposes_manifest_without_node_bodies(tmp_path, monkeypatch):
    import copy
    import config as cfgmod

    main, brain, _ = _brain_with_workflow(
        tmp_path, monkeypatch, copy.deepcopy(cfgmod._DEFAULT))
    manifests = main.workflow_manifests("brain")
    assert len(manifests) == 1
    item = manifests[0]
    assert item["slug"] == "demo" and item["node_count"] == 2
    assert item["max_risk"] == "none" and item["resumable"] is True
    assert item["input_contract"]["derived"] and item["output_contract"]["derived"]
    # Thân prompt của node KHÔNG được lọt vào manifest.
    blob = json.dumps(item, ensure_ascii=False)
    assert "Tìm {{input}}" not in blob and "Viết từ" not in blob


def test_failure_after_events_does_not_run_the_workflow_twice(tmp_path, monkeypatch):
    """Lỗi giữa chừng KHÔNG được kéo theo một lượt legacy đầy đủ nữa."""
    import copy
    import config as cfgmod

    on = copy.deepcopy(cfgmod._DEFAULT)
    on["context_runtime"]["mode"] = "canary"
    on["context_runtime"]["workflow_canary"].update(
        {"allocation_basis_points": 10_000, "allowed_slugs": ["demo"]})
    main, brain, calls = _brain_with_workflow(tmp_path, monkeypatch, on)

    async def half_then_boom(brain_, slug, input_="", tools=None, session_id=""):
        yield {"type": "start", "workflow": "Demo", "steps": 2}
        yield {"type": "step_done", "node": "s0", "output": "KQ(1)"}
        raise RuntimeError("đứt giữa chừng")

    monkeypatch.setattr(main, "execute_workflow_graph", half_then_boom)
    events = _drain(main.execute_workflow("brain", "demo", input="x", session_id="s"))
    assert not calls, "không được chạy lại bằng runner cũ sau khi đã phát event"
    assert events[-1]["type"] == "error"


def test_each_brain_loads_its_own_nested_workflows(tmp_path, monkeypatch):
    """graph_loader ôm ĐỊNH DANH brain, nên một canary dùng chung sẽ nạp nhầm brain.

    Test phải để `_workflows_dir` TÔN TRỌNG tham số brain, nếu không nó chỉ đo lại
    chính cái monkeypatch của mình chứ không đo sự cô lập giữa các brain.
    """
    import main

    roots = {}
    for name, task in (("brain-a", "A {{input}}"), ("brain-b", "B {{input}}")):
        root = tmp_path / name
        (root / "workflows").mkdir(parents=True)
        (root / "workflows" / "demo.md").write_text(
            f"---\ntype: workflow\nname: {name}\nslug: demo\nstatus: active\n"
            f"steps:\n  - agent: researcher\n    task: '{task}'\n---\n",
            encoding="utf-8")
        roots[name] = root

    monkeypatch.setattr(main, "_workflows_dir", lambda b: roots[b] / "workflows")

    a = main._get_workflow_canary("brain-a").graph_loader("demo")
    b = main._get_workflow_canary("brain-b").graph_loader("demo")
    assert a is not None and b is not None
    assert a.name == "brain-a" and b.name == "brain-b"
    assert a.revision != b.revision, "mỗi brain phải ra đồ thị của chính nó"


def test_graph_path_events_carry_the_step_index_studio_needs(tmp_path, monkeypatch):
    """Studio định vị chỗ đổ chữ bằng `i`. Thiếu nó thì chữ bị vứt lặng lẽ."""
    import copy
    import config as cfgmod

    on = copy.deepcopy(cfgmod._DEFAULT)
    on["context_runtime"]["mode"] = "canary"
    on["context_runtime"]["workflow_canary"].update(
        {"allocation_basis_points": 10_000, "allowed_slugs": ["demo"]})
    main, brain, _ = _brain_with_workflow(tmp_path, monkeypatch, on)

    class StreamingEngine:
        def __init__(self, *a, **k):
            self.model = None

        async def query(self, prompt):
            yield {"type": "text", "content": "từng"}
            yield {"type": "tool_call", "name": "Read"}
            yield {"type": "final", "content": "xong"}

    monkeypatch.setattr(main, "claude_engine", lambda **k: StreamingEngine())
    events = _drain(main.execute_workflow("brain", "demo", input="x", session_id="s"))

    streamed = [x for x in events if x["type"] in
                ("step_text", "step_tool", "step_start", "step_done")]
    assert streamed, "phải có event bước"
    for event in streamed:
        assert "i" in event, f"{event['type']} thiếu chỉ số bước"
        assert isinstance(event["i"], int)
    # Và chỉ số phải trỏ đúng bước, không phải luôn là 0.
    assert {x["i"] for x in streamed if x["type"] == "step_text"} == {0, 1}


def test_studio_handles_every_event_type_the_graph_path_emits():
    """Event phát ra mà giao diện không xử lý = người dùng không thấy gì.

    Đây đúng loại lỗi mà test phía server không bắt được, vì server vẫn phát đủ.
    """
    import re as _re
    from pathlib import Path

    studio = (Path(__file__).resolve().parents[2] / "dashboard" / "studio.js").read_text(
        encoding="utf-8")
    handled = set(_re.findall(r'd\.type === "([a-z_]+)"', studio))
    # Mọi loại event mà execute_workflow_graph / workflow_runtime / agent_runtime phát.
    emitted = {"start", "step_start", "step_text", "step_tool", "step_done",
               "step_error", "step_verify", "step_verify_result", "step_retry",
               "step_model", "resume", "replan", "wait_user", "escalation",
               "error", "done"}
    missing = emitted - handled
    assert not missing, f"Studio chưa xử lý: {sorted(missing)}"


def test_paused_workflow_is_not_shown_as_a_crash():
    """Dừng chờ duyệt phải đóng stream VÀ nói rõ, không im lặng như bị sập."""
    from pathlib import Path

    studio = (Path(__file__).resolve().parents[2] / "dashboard" / "studio.js").read_text(
        encoding="utf-8")
    block = studio.split('d.type === "wait_user"', 1)[1].split("} else if", 1)[0]
    assert "es.close()" in block and "endRun()" in block
    # Xưng hô đổi sang "bạn" (2026-08-14); 0.52.0 câu dời vào từ điển i18n. Test bám vào Ý
    # ("đang chờ duyệt"): khối phải nhắc khoá, và giá trị tiếng Việt của khoá phải còn nguyên ý.
    assert 't("studio.wait1")' in block
    vi = (Path(__file__).resolve().parents[2] / "dashboard" / "i18n" / "vi.json").read_text(
        encoding="utf-8")
    assert "chờ bạn duyệt" in vi


def test_kanban_marks_a_paused_workflow_as_needing_a_person(tmp_path):
    """Task chạy workflow mà dừng chờ duyệt KHÔNG được chấm là xong với kết quả rỗng.

    Chạy thật `_execute` với một execute_workflow giả, không quét chuỗi source.
    """
    from tasks import TasksDeps, TasksFeature

    async def paused_workflow(brain_root, slug, intent, tools):
        yield {"type": "start", "workflow": "demo", "steps": 2}
        yield {"type": "step_done", "i": 0, "output": "đã soạn xong"}
        yield {"type": "wait_user", "node": "w", "reason": "write_node_needs_confirmation",
               "prompt": "Gửi email cho khách?"}

    feature = TasksFeature(TasksDeps(
        brain_root=lambda b: str(tmp_path),
        atomic_write_text=lambda path, text: None,
        execute_workflow=paused_workflow,
        workflows_dir=lambda b: tmp_path,
        build_system_prompt=lambda b: "",
        aux_model=lambda: None,
        safe_tools=[],
        state_dir=tmp_path,
    ))
    result, error, needs_input, _meta = asyncio.run(feature._execute({
        "route": "wf:demo", "intent": "gửi báo cáo", "brain_root": str(tmp_path),
    }))
    assert needs_input is True, "phải chuyển sang trạng thái cần người"
    assert not error
    assert "[[NEEDS_INPUT]]" in result and "chờ duyệt" in result
    assert "Gửi email cho khách?" in result, "phải nói rõ đang chờ duyệt việc gì"


def test_kanban_surfaces_an_agent_escalation_too(tmp_path):
    from tasks import TasksDeps, TasksFeature

    async def escalating(brain_root, slug, intent, tools):
        yield {"type": "escalation", "reason": "repeated_failure_signature"}

    feature = TasksFeature(TasksDeps(
        brain_root=lambda b: str(tmp_path),
        atomic_write_text=lambda path, text: None,
        execute_workflow=escalating, workflows_dir=lambda b: tmp_path,
        build_system_prompt=lambda b: "", aux_model=lambda: None,
        safe_tools=[], state_dir=tmp_path,
    ))
    result, _error, needs_input, _meta = asyncio.run(feature._execute({
        "route": "wf:demo", "intent": "x", "brain_root": str(tmp_path),
    }))
    assert needs_input is True and "repeated_failure_signature" in result


def test_studio_offers_an_approve_button_carrying_the_code():
    """Cùng nguyên tắc với đường write trong chat: nhãn nút mang mã của đúng node.

    Nếu nút chỉ là "Duyệt" trơn thì nó duyệt được bất cứ thứ gì đang chờ.
    """
    from pathlib import Path

    studio = (Path(__file__).resolve().parents[2] / "dashboard" / "studio.js").read_text(
        encoding="utf-8")
    block = studio.split('d.type === "wait_user"', 1)[1].split("} else if", 1)[0]
    assert "wf-approve" in block
    assert '${esc(t("studio.approve"))} ${esc(d.code)}' in block, "nhãn nút phải mang mã"
    assert 't("studio.wait_warn")' in block, "phải cảnh báo trước khi bấm"
    # Và cú bấm gửi đủ ba thứ định danh, không đoán bên server.
    handler = studio.split("wf-approve", 2)[2]
    for field in ("task_id", "node", "code"):
        assert field in handler, field


def test_resume_endpoint_refuses_a_task_it_cannot_resume(tmp_path, monkeypatch):
    """Task không tồn tại thì báo lỗi rõ, không im lặng chạy gì cả."""
    import main

    async def go():
        return [x async for x in main.execute_workflow_resume(
            "brain", "demo", "khong-co-task", "w", "ABC123")]

    monkeypatch.setattr(main, "load_workflow_graph",
                        lambda b, s: wg.compile_workflow(LEGACY, "demo"))
    events = asyncio.run(go())
    assert events and events[0]["type"] == "error"


def test_main_capability_runner_refuses_a_write_before_approval(tmp_path, monkeypatch):
    """Hàng rào CUỐI trong main.py: kể cả tầng trên có lỗi logic, chưa duyệt là không chạy.

    Đây là đường đi thật (qua mcp_hub), không phải runner giả của test.
    """
    import copy
    import config as cfgmod
    import main

    settings = copy.deepcopy(cfgmod._DEFAULT)
    settings["context_runtime"]["mode"] = "canary"
    settings["context_runtime"]["workflow_canary"].update({
        "allocation_basis_points": 10_000, "allowed_slugs": ["demo"],
        "allow_write_nodes": True})

    brain = tmp_path / "brain"
    (brain / "workflows").mkdir(parents=True)
    (brain / "agents").mkdir(parents=True)
    (brain / "workflows" / "demo.md").write_text(
        "---\ntype: workflow\nname: Demo\nslug: demo\nstatus: active\n"
        "nodes:\n"
        "  - id: w\n    kind: capability\n    capability: mail_send\n"
        "    effect: write\n    arguments: {to: 'a@b.c'}\n---\n", encoding="utf-8")

    sent = []

    async def mail_send(args):
        sent.append(args)
        return "đã gửi"

    async def fake_discover(mode, vault_root=None, **kwargs):
        route = {"mail_send": {"effect": "write", "required_mode": "safe",
                               "health": "healthy", "call": mail_send}}
        return list(route.keys()), route

    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_workflows_dir", lambda b: brain / "workflows")
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda *a, **k: None)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: settings)
    monkeypatch.setattr(main.mcp_hub, "discover_all", fake_discover)

    events = _drain(main.execute_workflow_graph("brain", "demo", "x", None, "sid-w"))
    waits = [x for x in events if x["type"] == "wait_user"]
    assert waits, "phải dừng hỏi trước node ghi"
    assert not sent, "tool ghi tuyệt đối không được gọi khi chưa duyệt"
    assert waits[0].get("code"), "phải kèm mã để duyệt"


def test_the_second_layer_write_guard_is_testable_and_works():
    """Lớp thứ hai không bao giờ chạm tới ở luồng bình thường, nên phải kiểm riêng."""
    import main

    node = wg.compile_workflow({"name": "x", "nodes": [
        {"id": "w", "kind": "capability", "capability": "mail_send", "effect": "write"}]},
        "demo").nodes[0]

    async def call(args):
        return "ok"

    write_route = {"effect": "write", "call": call}
    read_route = {"effect": "read", "call": call}

    assert main.workflow_capability_guard(node, write_route, False) == "write_without_approval"
    assert main.workflow_capability_guard(node, write_route, True) == ""
    assert main.workflow_capability_guard(node, read_route, False) == ""
    assert main.workflow_capability_guard(node, None, True) == "capability_route_missing"
    assert main.workflow_capability_guard(node, {"effect": "write"}, True) == "capability_route_missing"
    assert "effect_not_allowed" in main.workflow_capability_guard(
        node, {"effect": "dangerous", "call": call}, True)


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
