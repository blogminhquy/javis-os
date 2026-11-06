"""Owner decisions, internal failures and partial closure are separate durable states.

Fixtures only; no model, customer messages, production data or network.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import subprocess
import sys

import pytest

import task_attention
from task_store import TaskStore
from tasks import TasksDeps, TasksFeature, _BUCKET_SEP


def decision(**changes):
    value = {"kind": "choice", "question": "Which approved account should receive the report?",
             "owner_only_reason": "Only the owner can choose the intended personal recipient.",
             "options": ["Personal account", "Keep this task paused"]}
    value.update(changes)
    return "[[NEEDS_INPUT]] " + json.dumps(value)


@pytest.mark.parametrize("text", [
    "[[NEEDS_INPUT]] Editorial QA failed", "[[NEEDS_INPUT]] Missing source; research not finished",
    "[[NEEDS_INPUT]] Please fix replay/recovery", "[[NEEDS_INPUT]] not-json",
    decision(question="How should restart recovery be fixed?"),
    decision(owner_only_reason="Missing source or evidence must be investigated."),
    decision(options=["Proceed"]), decision(options=["Same", "same"]),
    decision(kind="engineering"), decision(question="Engineering work is unfinished."),
])
def test_non_decisions_never_become_owner_questions(text):
    assert task_attention.owner_request(text) is None


def test_owner_question_has_explicit_choices_and_no_effect_grant():
    request = task_attention.owner_request(decision())
    assert request and request["kind"] == "choice"
    assert "1. Personal account" in task_attention.question_text(request)
    assert "permission" not in request


def feature(tmp_path):
    root = tmp_path / "brain"
    root.mkdir(exist_ok=True)
    reports = []

    async def report(chat, text, **kwargs):
        reports.append({"chat": chat, "text": text, **kwargs})
        return True

    async def workflow(*args, **kwargs):
        if False:
            yield {}

    f = TasksFeature(TasksDeps(brain_root=lambda value: str(root),
        atomic_write_text=lambda p, t: None, execute_workflow=workflow,
        workflows_dir=lambda b: root / "workflows", build_system_prompt=lambda b: "",
        aux_model=lambda: None, safe_tools=["Read"], state_dir=tmp_path / "state", report=report))
    f._ensure(str(root))
    return f, root, reports


def run(f, root, result, *, passed=True, needs_input=False):
    tid = f.store.enqueue(str(root), "Synthetic task", "Fixture", capability="files", status="ready")

    async def execute(task): return result, "", needs_input, {}
    async def check(task, output): return passed, "Regression test failed", "fixture"
    f._execute, f._check_acceptance = execute, check
    claimed = f.store.claim(tid, "worker")
    asyncio.run(f._run_worker(claimed, "worker"))
    return f.store.get_task(tid)


def test_failed_quality_is_internal_and_preserves_history(tmp_path):
    f, root, reports = feature(tmp_path)
    try:
        task = run(f, root, "Partial work; tests not complete", passed=False)
        assert (task["status"], task["block_kind"]) == ("blocked", "acceptance")
        assert task["metadata"]["acceptance_check"] == "failed"
        assert not task["metadata"].get("qa") and not TaskStore.waits_for_owner(task)
        assert all(x.get("viec", {}).get("status") != "hoi" for x in reports)
        assert task["result"] == "Partial work; tests not complete"
        assert len(f.store.list_runs(task["id"])) == 1
    finally:
        f.store.close()


def test_failed_recheck_does_not_invent_a_question(tmp_path):
    s = TaskStore(tmp_path / "tasks.db")
    try:
        tid = s.enqueue(str(tmp_path), "Fixture", "Fixture", status="done")
        t = s.set_acceptance(tid, "failed", "Failed test, recovery proof missing")
        assert t["block_kind"] == "acceptance" and not t["metadata"].get("qa")
        assert not s.waits_for_owner(t)
    finally:
        s.close()


@pytest.mark.parametrize("result,owner", [(decision(), True), ("[[NEEDS_INPUT]] Missing source", False)])
def test_worker_escalation_contract(tmp_path, result, owner):
    f, root, reports = feature(tmp_path)
    try:
        t = run(f, root, result, needs_input=True)
        assert TaskStore.waits_for_owner(t) == owner
        assert (t["block_kind"] == "needs_input") == owner
        if owner:
            assert t["metadata"]["owner_request"]["options"] == ["Personal account", "Keep this task paused"]
            assert len([x for x in reports if x.get("viec", {}).get("status") == "hoi"]) == 1
    finally:
        f.store.close()


def test_partial_close_is_idempotent_durable_and_not_quality_pass(tmp_path):
    path = tmp_path / "tasks.db"
    s = TaskStore(path)
    parent = s.enqueue(str(tmp_path), "Pilot", "Fixture", status="ready")
    s.claim(parent, "worker")
    s.ask(parent, "worker", "Old question", extra_meta={"acceptance_check": "failed"})
    child = s.enqueue(str(tmp_path), "UAT", "Fixture", deps=[parent], status="todo")
    other = s.enqueue(str(tmp_path), "Other", "Do not modify", status="blocked")
    before = s.get_task(parent)
    try:
        assert not s.close_partial(parent, "owner-receipt.json", "a" * 64, expected_updated_at=0)
        assert s.promote_dependencies(str(tmp_path)) == 0
        assert s.close_partial(parent, "owner-receipt.json", "a" * 64, expected_updated_at=before["updated_at"])
        assert s.close_partial(parent, "owner-receipt.json", "a" * 64, expected_updated_at=before["updated_at"])
        assert len([x for x in s.list_events(parent) if x["event_type"] == "owner_closed_partial"]) == 1
        assert s.promote_dependencies(str(tmp_path)) == 1
        assert s.promote_dependencies(str(tmp_path)) == 0
        t = s.get_task(parent)
        assert t["status"] == "archived" and t["metadata"]["owner_closure"]["outcome"] == "partial"
        assert t["metadata"]["acceptance_check"] == "failed" and t["metadata"]["qa"] == before["metadata"]["qa"]
        assert s.get_task(child)["status"] == "ready" and s.get_task(child)["deps"] == [parent]
        assert s.get_task(other)["status"] == "blocked"
        assert s.set_acceptance(parent, "failed", "stale callback") is None
    finally:
        s.close()
    s = TaskStore(path)
    try:
        assert s.get_task(parent)["metadata"]["owner_closure"]["execution_status"] == "CLOSED_PER_OWNER_DECISION"
        assert s.get_task(child)["status"] == "ready" and s.promote_dependencies(str(tmp_path)) == 0
    finally:
        s.close()


def test_receipt_text_cannot_close_a_running_task(tmp_path):
    s = TaskStore(tmp_path / "tasks.db")
    try:
        tid = s.enqueue(str(tmp_path), "Pilot", "Fixture", status="ready")
        t = s.claim(tid, "worker")
        assert not s.close_partial(tid, "receipt.json", "a" * 64, expected_updated_at=t["updated_at"])
        assert s.get_task(tid)["status"] == "running"
    finally:
        s.close()


def test_pending_question_replay_keeps_notification_key_across_restart(tmp_path):
    f, root, reports = feature(tmp_path)
    tid = f.store.enqueue(str(root), "Decision", "Fixture", capability="files", status="ready")
    f.store.claim(tid, "worker")
    t = f.store.ask(tid, "worker", "Which account?\n1. Personal\n2. Hold")
    asyncio.run(f._report(t))
    first = reports[-1]["dedup"]
    f.store.move(tid, "ready")
    f.store.claim(tid, "worker")
    again = f.store.ask(tid, "worker", "Which account?\n1. Personal\n2. Hold")
    assert len(again["metadata"]["qa"]) == 1
    f.store.close()
    f, root, reports = feature(tmp_path)
    try:
        asyncio.run(f._report(f.store.get_task(tid)))
        assert reports[-1]["dedup"] == first
        latest = f.store.get_task(tid)
        assert f.store.close_partial(tid, "receipt.json", "a" * 64, expected_updated_at=latest["updated_at"])
        count = len(reports)
        asyncio.run(f._report(latest))
        asyncio.run(f._bao_cau_hoi(latest))
        assert len(reports) == count
    finally:
        f.store.close()


def test_internal_batch_dedup_and_stale_timer(tmp_path):
    f, root, reports = feature(tmp_path)
    tid = f.store.enqueue(str(root), "Engineering", "Fixture", status="ready", capability="files")
    f.store.claim(tid, "worker")
    t = f.store.block(tid, "worker", "engineering", "Replay proof missing")

    async def flush():
        await f._gom_bao(t)
        await f._gom_bao(t)
        key = _BUCKET_SEP + str(root)
        assert len(f._ro_bao[key]) == 1
        timer = f._hen_bao[key]
        await f._xa_bao(key)
        timer.cancel()
        await asyncio.gather(timer, return_exceptions=True)

    try:
        asyncio.run(flush())
        assert len(reports) == 1 and reports[-1]["quiet"] is True
        key = reports[-1]["dedup"]
        asyncio.run(flush())
        assert reports[-1]["dedup"] == key
        # A pending timer after closure sends nothing about the old blocked state.
        assert f.store.close_partial(tid, "receipt.json", "a" * 64, expected_updated_at=t["updated_at"])
        count = len(reports)
        asyncio.run(f._report(t))
        assert len(reports) == count
    finally:
        f.store.close()


def test_replay_in_a_new_process_keeps_one_native_inbox_record(tmp_path):
    """Exercise persisted SQLite + the existing inbox dedup in two separate processes."""
    code = r'''
import asyncio,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from task_store import TaskStore
from tasks import TasksFeature,TasksDeps
import inbox
root=pathlib.Path(sys.argv[2]);root.mkdir(exist_ok=True)
inbox.STORE=root/'inbox.json'
async def report(chat,text,**kw):
    return inbox.add(text,brain=str(root),dedup=kw['dedup'])
async def workflow(*a,**kw):
    if False:yield {}
f=TasksFeature(TasksDeps(brain_root=lambda _:str(root),atomic_write_text=lambda *a:None,
 execute_workflow=workflow,workflows_dir=lambda _:root/'workflows',build_system_prompt=lambda _: '',
 aux_model=lambda:None,safe_tools=['Read'],state_dir=root/'state',report=report))
ids=f.store.list_tasks(str(root))
if not ids:
    tid=f.store.enqueue(str(root),'Owner decision','Fixture',status='ready',capability='files')
    f.store.claim(tid,'worker');task=f.store.ask(tid,'worker','Which account? 1. Personal 2. Hold')
else:task=ids[0]
asyncio.run(f._report(task))
print(json.dumps({'count':len(inbox.danh_sach()),'id':task['id']}))
f.store.close()
'''
    env = {**os.environ, "JAVIS_STATE_DIR": str(tmp_path / "state"), "BRAINS_DIR": str(tmp_path / "brains")}
    receipts = []
    for _ in range(2):
        p = subprocess.run([sys.executable, "-c", code, str(SERVER), str(tmp_path / "fixture")],
                           env=env, capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, p.stderr
        receipts.append(json.loads(p.stdout.strip().splitlines()[-1]))
    assert receipts[0] == receipts[1] and receipts[1]["count"] == 1


def test_partial_move_route_is_brain_scoped_and_compare_and_set(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    f, root, _reports = feature(tmp_path)
    app = FastAPI()
    app.include_router(f.router)
    parent = f.store.enqueue(str(root), "Pilot", "Fixture", status="blocked")
    other = f.store.enqueue(str(tmp_path / "other-brain"), "Other", "Fixture", status="blocked")
    try:
        with TestClient(app) as client:
            data = {"id": other, "status": "archived", "brain": str(root), "outcome": "partial",
                    "decision_ref": "owner-receipt.json", "decision_sha256": "a" * 64,
                    "expected_updated_at": f.store.get_task(other)["updated_at"]}
            assert not client.post("/kanban/task/move", data=data).json()["ok"]
            data["id"] = parent
            data["expected_updated_at"] = 0
            assert not client.post("/kanban/task/move", data=data).json()["ok"]
            data["expected_updated_at"] = f.store.get_task(parent)["updated_at"]
            assert client.post("/kanban/task/move", data=data).json()["ok"]
            assert f.store.get_task(parent)["metadata"]["owner_closure"]["outcome"] == "partial"
            assert f.store.get_task(other)["status"] == "blocked"
    finally:
        f.store.close()


def test_explicit_workflow_approval_supplies_a_real_question_and_options(tmp_path):
    f, root, _reports = feature(tmp_path)

    async def workflow(*args, **kwargs):
        yield {"type": "wait_user", "node": "review", "prompt": "Approve this draft"}

    f.deps.execute_workflow = workflow
    try:
        result, error, needs_input, _ = asyncio.run(f._execute({
            "brain_root": str(root), "route": "wf:review", "capability": "files"}))
        request = task_attention.owner_request(result)
        assert not error and needs_input and request["kind"] == "approval"
        assert request["question"] == "Approve this draft?" and len(request["options"]) == 2
    finally:
        f.store.close()


@pytest.mark.parametrize("kind", ["error", "escalation"])
def test_workflow_technical_escalation_does_not_become_owner_approval(tmp_path, kind):
    f, root, _reports = feature(tmp_path)

    async def workflow(*args, **kwargs):
        yield {"type": kind, "needs_input": True, "content": "Replay test failed", "reason": "Replay test failed"}

    f.deps.execute_workflow = workflow
    try:
        _result, error, needs_input, _ = asyncio.run(f._execute({
            "brain_root": str(root), "route": "wf:review", "capability": "files"}))
        assert error == "Replay test failed" and not needs_input
    finally:
        f.store.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
