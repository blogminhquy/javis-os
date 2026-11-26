"""A background job never hangs silently (issue 1841).

    python tests/run.py workflow_stop_asks_owner        (no network, no model call)

When the owner can resolve why a Kanban job stopped (a workflow step still fails its check after the last retry, the
workflow waits for an approval or hands the run back to a person), the job becomes a question to the owner: blocked as
`needs_input` with a Q&A row, shown on the Tasks page and in the bell. Before, the linear runner sent `step_error` and
then `error` + `needs_input` with the same text; the worker read the step error first and retried the job in silence
(the verifier's reason said "timeout") or blocked it with no question. The graph runner ended the same stop with
`done` and an empty result.

Both runners are driven for real with fake engines; their event streams then go through the real Kanban worker.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import copy
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-wf-stop-"))

import pytest  # noqa: E402

from tasks import TasksDeps, TasksFeature, workflow_stops_for_owner  # noqa: E402

# The verifier's reason carries "timeout": the old worker took the step error for a network blip and retried at once.
FAIL = '{"pass": false, "reason": "trang giá bị timeout nên bài thiếu giá", "fixes": "thêm giá"}'
PASS = '{"pass": true, "reason": "ok"}'


def _drain(gen):
    async def go():
        return [x async for x in gen]
    return asyncio.run(go())


def _workflow_brain(tmp_path, monkeypatch, verify_answers, graph=False):
    """A two-step workflow whose first step has a verifier; the real runner of main.py with fake engines."""
    import config as cfgmod
    import main

    brain = tmp_path / "brain"
    (brain / "workflows").mkdir(parents=True)
    (brain / "agents").mkdir(parents=True)
    (brain / "workflows" / "demo.md").write_text(
        "---\ntype: workflow\nname: Demo\nslug: demo\nstatus: active\nsteps:\n"
        "  - agent: writer\n    task: 'Viết {{input}}'\n    verify_agent: checker\n    max_retries: 1\n"
        "  - agent: poster\n    task: 'Đăng {{prev}}'\n---\n", encoding="utf-8")
    for slug in ("writer", "checker", "poster"):
        (brain / "agents" / f"{slug}.md").write_text(
            f"---\ntype: agent\nname: {slug}\nslug: {slug}\nrole: r\nskills: []\n---\nbody\n", encoding="utf-8")
    calls = []
    answers = list(verify_answers)

    class FakeEngine:
        def __init__(self, **k):
            self.model = None

        async def query(self, prompt):
            calls.append(prompt)
            if "KẾT QUẢ CẦN KIỂM CHỨNG" in prompt:
                yield {"type": "final", "content": answers.pop(0) if answers else ""}
                return
            yield {"type": "final", "content": f"draft {len(calls)}"}

    settings = copy.deepcopy(cfgmod._DEFAULT)
    if graph:
        settings["context_runtime"]["mode"] = "canary"
        settings["context_runtime"]["workflow_canary"].update({
            "allocation_basis_points": 10_000, "allowed_slugs": ["demo"]})
    monkeypatch.setattr(main, "claude_engine", lambda **k: FakeEngine(**k))
    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_workflows_dir", lambda b: brain / "workflows")
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    monkeypatch.setattr(main, "_log_agent_run", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda *a, **k: None)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: settings)
    return main, calls


async def _report(*_a, **_k):
    return True


def _job_after(tmp_path, events):
    """Replay a workflow's events through the real Kanban worker; the job as the store holds it afterwards."""
    async def workflow(*_a, **_k):
        for ev in events:
            yield ev

    brain = tmp_path / "kanban-brain"
    brain.mkdir(parents=True, exist_ok=True)

    def atomic(path, text):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")

    feature = TasksFeature(TasksDeps(
        brain_root=lambda v: str(brain), atomic_write_text=atomic, execute_workflow=workflow,
        workflows_dir=lambda b: Path(brain) / "workflows", build_system_prompt=lambda b: "system",
        aux_model=lambda: None, safe_tools=["Read", "Write"], state_dir=tmp_path / "kanban-state",
        scheduler_brains=lambda: [str(brain)], report=_report))
    root = feature._ensure(str(brain))
    tid = feature.store.enqueue(root, "Bài S07", "chạy quy trình", capability="files", status="ready",
                                route="wf:demo")
    claimed = feature.store.claim(tid, "w")
    assert claimed
    asyncio.run(feature._run_worker(claimed, "w"))
    job = feature.store.get_task(tid)
    feature.store.close()
    return job


def _assert_question(job, *needles):
    assert job["status"] == "blocked" and job["block_kind"] == "needs_input", (
        job["status"], job["block_kind"], job["block_reason"])
    qa = (job.get("metadata") or {}).get("qa") or []
    assert qa and not qa[-1].get("a"), "the owner gets a question to answer"
    for needle in needles:
        assert needle in qa[-1]["q"], qa[-1]["q"]


# ---------------------------------------------------------------- linear runner

def test_linear_verify_failure_becomes_a_question(tmp_path, monkeypatch):
    main, calls = _workflow_brain(tmp_path, monkeypatch, [FAIL, FAIL])
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07", tools=["Read"], mode="auto"))
    kinds = [e["type"] for e in events]
    # The real sequence: the step's own error row, then the run's stop for the owner, and nothing after.
    assert kinds[-2:] == ["step_error", "error"] and events[-1].get("needs_input"), kinds
    assert events[-2]["content"] == events[-1]["content"]
    assert not any(p.startswith("Đăng") for p in calls), "the next step does not run"
    job = _job_after(tmp_path, events)
    _assert_question(job, "thiếu giá")


def test_linear_pass_still_finishes(tmp_path, monkeypatch):
    main, _ = _workflow_brain(tmp_path, monkeypatch, [PASS])
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07"))
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------- graph runner

def test_graph_verify_failure_ends_as_a_question_not_done(tmp_path, monkeypatch):
    main, calls = _workflow_brain(tmp_path, monkeypatch, [FAIL, FAIL], graph=True)
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07", tools=["Read"], mode="auto"))
    assert any(e.get("node") for e in events if e["type"] == "step_start"), "the graph runner ran"
    kinds = [e["type"] for e in events]
    assert "done" not in kinds, "a run stopped on a failed check is not done"
    last = events[-1]
    assert last["type"] == "error" and last.get("needs_input") and "thiếu giá" in last["content"], last
    assert last.get("i") == 0 and last.get("agent") == "writer", last
    assert not any(p.startswith("Đăng") for p in calls), "the next step does not run"
    job = _job_after(tmp_path, events)
    _assert_question(job, "thiếu giá")


def test_graph_pass_still_ends_done(tmp_path, monkeypatch):
    main, calls = _workflow_brain(tmp_path, monkeypatch, [PASS], graph=True)
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07"))
    assert any(e.get("node") for e in events if e["type"] == "step_start"), "the graph runner ran"
    assert events[-1]["type"] == "done" and events[-1]["result"], events[-1]
    assert not [e for e in events if e["type"] == "error"]


def test_graph_engine_failure_is_not_turned_into_a_question():
    """Only a failed CHECK is the owner's to answer: a step that broke on a timeout keeps the old ending."""
    import main
    from types import SimpleNamespace

    class Canary:
        def __init__(self, nodes):
            self.nodes = nodes

        def load_state(self, task_id):
            return {"nodes": self.nodes}

    graph = SimpleNamespace(node=lambda nid: None)
    stopped = SimpleNamespace(status="FAILED", stop_reason="node_failed", task_id="t1")
    verify = {"status": "FAILED", "verified": False, "error": "Bước 1 chưa qua kiểm chứng"}
    timeout = {"status": "FAILED", "verified": None, "error": "node_timeout"}
    assert main._graph_owner_stop(Canary({"a": verify}), graph, stopped)["needs_input"] is True
    assert main._graph_owner_stop(Canary({"a": verify, "b": timeout}), graph, stopped) is None
    assert main._graph_owner_stop(Canary({"b": timeout}), graph, stopped) is None
    runtime_stop = SimpleNamespace(status="FAILED", stop_reason="checkpoint_failed", task_id="t1")
    assert main._graph_owner_stop(Canary({"a": verify}), graph, runtime_stop) is None
    done = SimpleNamespace(status="COMPLETED", stop_reason="objective_satisfied", task_id="t1")
    assert main._graph_owner_stop(Canary({"a": verify}), graph, done) is None


# ---------------------------------------------------------------- every stop for the owner

@pytest.mark.parametrize("stop", [
    {"type": "wait_user", "node": "w", "prompt": "Gửi email cho khách?"},
    {"type": "escalation", "reason": "Agent gặp lại đúng một lỗi nhiều lần"},
    {"type": "error", "needs_input": True, "content": "Quy trình 'Demo' đang tắt"},
])
def test_a_step_error_before_a_stop_for_the_owner_does_not_win(tmp_path, stop):
    events = [{"type": "start", "workflow": "Demo", "steps": 2},
              {"type": "step_start", "i": 0, "agent": "writer"},
              {"type": "step_error", "i": 0, "content": "connection reset while fetching the price page"},
              stop]
    assert workflow_stops_for_owner(stop)
    job = _job_after(tmp_path, events)
    _assert_question(job)


def test_a_webhook_workflow_that_stops_for_the_owner_is_waiting_not_failed(monkeypatch):
    import main

    async def stopped(*_a, **_k):
        yield {"type": "step_error", "i": 0, "content": "Bước 1 chưa qua kiểm chứng: thiếu giá"}
        yield {"type": "error", "i": 0, "needs_input": True, "content": "Bước 1 chưa qua kiểm chứng: thiếu giá"}

    monkeypatch.setattr(main, "execute_workflow", stopped)
    result, error, needs_input = asyncio.run(main._webhook_run_workflow("brain", "demo", "x", "auto"))
    assert needs_input and not error and "thiếu giá" in result


def test_an_engine_error_alone_is_still_an_error(tmp_path):
    events = [{"type": "step_start", "i": 0},
              {"type": "step_error", "i": 0, "content": "engine crashed"},
              {"type": "error", "i": 0, "content": "engine crashed"}]
    assert not workflow_stops_for_owner(events[-1])
    job = _job_after(tmp_path, events)
    assert job["block_kind"] != "needs_input" and job["status"] in ("blocked", "ready"), job["status"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
