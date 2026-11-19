"""An approval answered on the Tasks page runs the workflow on from the step it stopped at.

    python tests/python/test_kanban_workflow_approval_resume.py

Owner, 17/11/2026: "SAO TÔI DUYỆT RỒI MÀ CỨ BÁO DUYỆT LẠI HOÀI VẬY". A workflow job queued on Kanban stops at an
approval step. Answering it used to start the workflow again from step one with the answer in the brief, and step one
leads straight back to the same approval step, so every "Duyệt" opened a new run that asked again (six runs of one job
on one afternoon). A plain approval now resumes the stopped run; a change request still starts again with the answer.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
from pathlib import Path

from tasks import TasksDeps, TasksFeature, la_loi_duyet


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _feature(tmp_path, calls, resume=True, resume_works=True, resume_stops_again=False):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)

    async def _workflow(_brain, slug, input="", tools=None, **_k):
        calls.append(("run", slug, input))
        yield {"type": "start"}
        yield {"type": "step_start", "node": "content"}
        yield {"type": "wait_user", "node": "duyet-content", "code": "ABC123", "task_id": "wft_1",
               "prompt": "DUYỆT CONTENT"}

    async def _resume(_brain, slug, task_id, node, code, tools=None, mode=None, source="other"):
        calls.append(("resume", slug, task_id, node, code))
        if not resume_works:
            yield {"type": "error", "content": "This task was not found or cannot be resumed."}
            return
        if resume_stops_again:
            # What the runtime does on a code mismatch: stands still and the wrapper yields wait_user with no code.
            yield {"type": "wait_user", "node": node, "task_id": task_id, "reason": "confirmation_code_mismatch"}
            return
        yield {"type": "resume", "reused": 2}
        yield {"type": "step_start", "node": "dung-clip"}
        yield {"type": "done", "result": "Đã qua mốc duyệt, chạy xong."}

    deps = TasksDeps(
        brain_root=lambda v: str(brain), atomic_write_text=_atomic, execute_workflow=_workflow,
        workflows_dir=lambda b: Path(brain) / "workflows", build_system_prompt=lambda b: "system",
        aux_model=lambda: None, safe_tools=["Read", "Write"], state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)],
        execute_workflow_resume=_resume if resume else None,
    )
    return TasksFeature(deps), str(brain)


async def _stop_at_gate(feature, brain):
    """Queue a workflow job and run it once: it stops at the approval step, as on the owner's board."""
    root = feature._ensure(brain)
    tid = feature.store.enqueue(root, "SKY tập 0", "chạy quy trình", capability="files", status="ready",
                                route="wf:san-xuat-clip-sky")
    task = feature.store.get_task(tid)
    result, error, needs_input, meta = await feature._execute(task)
    assert needs_input and not error
    assert feature.store.claim(tid, "w")
    feature.store.ask(tid, "w", "Workflow dừng chờ duyệt bước 'duyet-content'", result=result,
                      qa_extra={"wf_wait": meta["wf_wait"]})
    return tid


def test_plain_approval_resumes_instead_of_starting_again(tmp_path):
    calls = []
    feature, brain = _feature(tmp_path, calls)

    async def go():
        tid = await _stop_at_gate(feature, brain)
        ok, err = feature.store.answer(tid, "Duyệt V006.")
        assert ok and not err
        return await feature._execute(feature.store.get_task(tid))

    result, error, needs_input, _meta = asyncio.run(go())
    assert calls[0][0] == "run"
    assert calls[1] == ("resume", "san-xuat-clip-sky", "wft_1", "duyet-content", "ABC123")
    assert len(calls) == 2, calls                      # never a second fresh run
    assert not needs_input and not error
    assert "chạy xong" in result


def test_change_request_still_starts_again_with_the_answer(tmp_path):
    calls = []
    feature, brain = _feature(tmp_path, calls)

    async def go():
        tid = await _stop_at_gate(feature, brain)
        feature.store.answer(tid, "Chưa duyệt V004. Lập V005 đổi màu cyan.")
        return await feature._execute(feature.store.get_task(tid))

    asyncio.run(go())
    assert [c[0] for c in calls] == ["run", "run"]
    assert "Lập V005 đổi màu cyan" in calls[1][2]


def test_resume_that_cannot_pick_up_falls_back_to_the_old_path(tmp_path):
    calls = []
    feature, brain = _feature(tmp_path, calls, resume_works=False)

    async def go():
        tid = await _stop_at_gate(feature, brain)
        feature.store.answer(tid, "duyệt")
        return await feature._execute(feature.store.get_task(tid))

    _result, error, needs_input, _meta = asyncio.run(go())
    assert [c[0] for c in calls] == ["run", "resume", "run"]
    assert needs_input and not error                   # the job still waits for the owner, it does not end empty


def test_without_resume_wired_the_old_path_is_kept(tmp_path):
    calls = []
    feature, brain = _feature(tmp_path, calls, resume=False)

    async def go():
        tid = await _stop_at_gate(feature, brain)
        feature.store.answer(tid, "Duyệt")
        return await feature._execute(feature.store.get_task(tid))

    asyncio.run(go())
    assert [c[0] for c in calls] == ["run", "run"]


def test_resume_that_stops_again_keeps_the_confirmation_code(tmp_path):
    calls = []
    feature, brain = _feature(tmp_path, calls, resume_stops_again=True)

    async def go():
        tid = await _stop_at_gate(feature, brain)
        feature.store.answer(tid, "ok")
        return await feature._execute(feature.store.get_task(tid))

    _result, _error, _needs_input, meta = asyncio.run(go())
    assert [c[0] for c in calls] == ["run", "resume"]
    # Without the code the next approval would resume with "" and mismatch for ever.
    assert meta["wf_wait"] == {"task_id": "wft_1", "node": "duyet-content", "code": "ABC123",
                               "slug": "san-xuat-clip-sky"}, meta


def test_what_counts_as_a_plain_approval():
    for yes in ("Duyệt", "duyệt V006.", "Duyệt V006", "ok", "OK!", "Đồng ý", "đạt", "approve", "chạy tiếp"):
        assert la_loi_duyet(yes), yes
    for no in ("Chưa duyệt V004. Lập V005", "không duyệt", "duyệt nhưng sửa câu V06", "đừng duyệt",
               "Duyệt V006, đổi màu áo", "duyệt?", "", "Xem lại giúp anh", "ok but fix the logo"):
        assert not la_loi_duyet(no), no


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
