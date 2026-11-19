"""A `wf:` Kanban job whose step hits an exhausted plan waits for the reset instead of burning its attempts.

    python tests/python/test_kanban_workflow_limit.py

Issue 1607 (0.570.1): a workflow step turns "You've hit your limit · resets 4:40am" into a translated sentence before
the queue sees it. The queue's parser could not read that sentence, and `_is_transient` matched the bare word "reset"
in it, so the job went straight back to ready with no wait and spent all three attempts in about seven seconds. The
step now hands the parsed reset point over in its `error` event, and the queue defers the job to that point.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI  # noqa: F401  - same import environment as the other Kanban tests

import tasks as tasks_mod
from tasks import TasksDeps, TasksFeature

TRANSLATED = ("Gói Claude Code đã hết lượt trong cửa sổ hiện tại (nhà cung cấp nói: resets 4:40am). "
              "Muốn chạy ngay thì đổi sang model khác ở trang Models.")


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _report(*_a, **_k):
    return True


def _feature(tmp_path, workflow):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    deps = TasksDeps(
        brain_root=lambda v: str(brain), atomic_write_text=_atomic, execute_workflow=workflow,
        workflows_dir=lambda b: Path(brain) / "workflows", build_system_prompt=lambda b: "system",
        aux_model=lambda: None, safe_tools=["Read", "Write"], state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)], report=_report,
    )
    return TasksFeature(deps), str(brain)


def _run(feature, brain):
    root = feature._ensure(brain)
    tid = feature.store.enqueue(root, "Clip", "chạy quy trình", capability="files", status="ready",
                                route="wf:san-xuat-clip")
    claimed = feature.store.claim(tid, "w")
    assert claimed
    asyncio.run(feature._run_worker(claimed, "w"))
    return root, feature.store.get_task(tid)


def test_step_limit_defers_the_job_to_the_reset(tmp_path):
    reset = time.time() + 47 * 60

    async def workflow(*_a, **_k):
        yield {"type": "step_start", "i": 0}
        yield {"type": "step_error", "i": 0, "content": TRANSLATED}
        yield {"type": "error", "i": 0, "content": TRANSLATED,
               "limit": {"engine": "claude-code", "reset_epoch": reset, "reset_text": "resets 4:40am"}}

    feature, brain = _feature(tmp_path, workflow)
    root, t = _run(feature, brain)
    assert t["status"] == "ready" and t["block_kind"] == "limit", t
    wait = float(t["not_before"]) - time.time()
    assert 47 * 60 - 30 <= wait <= 47 * 60 + tasks_mod.LIMIT_GRACE_SECONDS + 30, wait
    assert int(t["attempts"]) == 0                       # the wait for a reset is not a failed attempt
    assert feature.store.next_candidate(root) is None   # the dispatcher does not pick it up again in seconds
    feature.store.close()


def test_step_limit_without_a_reset_time_waits_the_fixed_interval(tmp_path):
    async def workflow(*_a, **_k):
        yield {"type": "error", "i": 0, "content": TRANSLATED, "limit": {"engine": "codex", "reset_epoch": 0}}

    feature, brain = _feature(tmp_path, workflow)
    _root, t = _run(feature, brain)
    assert t["status"] == "ready" and t["block_kind"] == "limit", t
    wait = float(t["not_before"]) - time.time()
    assert tasks_mod.LIMIT_UNKNOWN_WAIT_SECONDS - 30 <= wait <= tasks_mod.LIMIT_UNKNOWN_WAIT_SECONDS + 5
    feature.store.close()


def test_plan_limit_sentence_is_not_a_transient_network_error():
    # The bare word "reset" used to make this look like a blip to retry at once.
    assert not TasksFeature._is_transient(TRANSLATED)
    assert TasksFeature._is_transient("ConnectionResetError: connection reset by peer")
    assert TasksFeature._is_transient("TimeoutError: timed out")


def test_meta_without_limit_is_ignored():
    assert TasksFeature._limit_from_meta(None) is None
    assert TasksFeature._limit_from_meta({"route": "wf:x"}) is None
    assert TasksFeature._limit_from_meta({"limit": {}}) is None
    hit = TasksFeature._limit_from_meta({"limit": {"engine": "claude-code", "reset_epoch": "123"}})
    assert hit and hit.engine == "claude-code" and hit.reset_epoch == 123.0


def test_workflow_step_error_carries_the_reset_point():
    src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
    assert "def _step_subscription_limit(" in src
    assert "step_limit = _step_subscription_limit(out, loi_engine, agent_prov)" in src
    assert 'err_ev["limit"] = step_limit' in src


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("skip: pytest is not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
