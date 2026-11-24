"""Kanban honesty: reject empty worker outputs and warn on unverified acceptance."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-pr3-"))

import localefmt  # noqa: E402
import pytest  # noqa: E402
from task_store import ACCEPTANCE_FAILED  # noqa: E402
from tasks import FIXED_ACCEPTANCE, TasksDeps, TasksFeature  # noqa: E402


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def _no_workflow(*_a, **_k):
    if False:
        yield {}


def _exec(text):
    return lambda _task: asyncio.sleep(0, result=(text, "", False, {}))


def _feature(tmp_path):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    reports = []

    async def report(*a, **k):
        reports.append((a, k))
        return True

    deps = TasksDeps(
        brain_root=lambda _b: str(brain), atomic_write_text=_atomic_write, execute_workflow=_no_workflow,
        workflows_dir=lambda _b: brain / "workflows", build_system_prompt=lambda _b: "", aux_model=lambda: None,
        safe_tools=["Read", "Write", "Edit", "Glob", "Grep", "LS"], state_dir=tmp_path / "state", report=report,
    )
    feature = TasksFeature(deps)
    feature._base_cli = lambda *a, **k: object()
    # One event loop for the whole life of this feature. TasksFeature keeps a per-brain asyncio.Lock (_asnapshot); one
    # first used on a loop cannot be awaited from another, and a fresh asyncio.run() per step made this file fail at
    # random on a loaded CI runner ("Lock ... is bound to a different event loop"). Production runs on one loop.
    feature._test_loop = asyncio.new_event_loop()
    return feature, str(brain), reports


def _run(feature, coro):
    return feature._test_loop.run_until_complete(coro)


def _enqueue(feature, brain, meta=None, needs_approval=False):
    tid = feature.store.enqueue(feature._ensure(brain), "Job", "produce report.md", capability="files",
                                status="ready", max_attempts=1, needs_approval=needs_approval, dedupe_title=False)
    if meta:
        with feature.store._lock:
            feature.store._db.execute("UPDATE tasks SET metadata_json=? WHERE id=?", (json.dumps(meta), tid))
            feature.store._db.commit()
    return tid


def _run_once(feature, tid, execute):
    feature._execute = execute

    async def go():
        assert await feature._claim_and_spawn(tid)
        worker = feature._workers.get(tid)
        if worker is not None:      # a fast worker may already have finished and removed itself
            await worker
        return feature.store.get_task(tid)

    return _run(feature, go())


@pytest.fixture(autouse=True)
def _english_ui():
    tok = localefmt.dat_ngon_ngu_yeu_cau("en")
    try:
        yield
    finally:
        localefmt.bo_ngon_ngu_yeu_cau(tok)


def test_verified_ai_pass_reports_green_check(tmp_path):
    feature, brain, reports = _feature(tmp_path)
    tid = _enqueue(feature, brain, {"acceptance": ["report.md exists"]})
    feature._query = lambda _cli, _p: asyncio.sleep(0, result=('{"pass": true, "missing": ""}', "", []))
    t = _run_once(feature, tid, _exec("Wrote report.md."))
    msg, kw = reports[0][0][1], reports[0][1]
    assert t["status"] == "done" and t["metadata"]["acceptance_check"] == "ai"
    assert msg.startswith("✅") and kw["quiet"] is True and kw["viec"]["acceptance_check"] == "ai"
    assert TasksFeature._calm(t) == ""
    feature.store.close()


def test_empty_output_retries_once_then_blocks_while_silent_stays_quiet(tmp_path):
    feature, brain, reports = _feature(tmp_path)
    tid = _enqueue(feature, brain, {"acceptance": ["report.md exists"]})
    passed, why, how = _run(feature, feature._check_acceptance(feature.store.get_task(tid), "  \n "))
    assert not passed and how == "empty" and "empty" in why.lower()

    first = _run_once(feature, tid, _exec("  \t "))
    assert first["status"] == "ready" and first["metadata"]["acceptance_fixes"] == 1 and not reports
    second = _run_once(feature, tid, _exec(""))
    assert second["status"] == "blocked" and second["block_kind"] == ACCEPTANCE_FAILED and len(reports) == 1

    silent_tid = _enqueue(feature, brain, {"acceptance": ["report.md exists"]})
    silent_task = _run_once(feature, silent_tid, _exec("[SILENT]"))
    assert silent_task["status"] == "done" and silent_task["metadata"]["silent"] is True
    assert silent_task["metadata"]["acceptance_check"] == "silent" and len(reports) == 1
    feature.store.close()


@pytest.mark.parametrize("reply", [("", "checker down"), ("not json", "")])
def test_checker_error_or_bad_json_warns_unverified(tmp_path, reply):
    feature, brain, reports = _feature(tmp_path)
    tid = _enqueue(feature, brain, {"acceptance": ["report.md exists"]})
    feature._query = lambda _cli, _p: asyncio.sleep(0, result=(reply[0], reply[1], []))
    t = _run_once(feature, tid, _exec("Finished draft."))
    msg, kw = reports[0][0][1], reports[0][1]
    assert t["status"] == "done" and t["metadata"]["acceptance_check"] == "unverified"
    assert msg.startswith("⚠") and not msg.startswith("✅") and "unverified" in msg.lower()
    assert kw["quiet"] is True and kw["viec"]["acceptance_check"] == "unverified"
    assert "checker failed" in TasksFeature._calm(t).lower()
    feature.store.close()


def test_review_task_with_unverified_checker_warns_honestly(tmp_path):
    feature, brain, reports = _feature(tmp_path)
    tid = _enqueue(feature, brain, {"acceptance": ["report.md exists"]}, needs_approval=True)
    feature._query = lambda _cli, _p: asyncio.sleep(0, result=("", "checker down", []))
    t = _run_once(feature, tid, _exec("Draft ready for approval."))
    msg, kw = reports[0][0][1], reports[0][1]
    assert t["status"] == "review" and t["metadata"]["acceptance_check"] == "unverified"
    assert msg.startswith("⚠") and not msg.startswith("✅")
    assert "review" in msg.lower() and "unverified" in msg.lower()
    assert kw["quiet"] is False and kw["viec"]["status"] == "review"
    assert kw["viec"]["acceptance_check"] == "unverified"
    calm_review = TasksFeature._calm(t)
    calm_done = TasksFeature._calm({**t, "status": "done"})
    assert "review" in calm_review.lower() and "unverified" in calm_review.lower()
    assert "checker failed" in calm_review.lower() and calm_review != calm_done
    feature.store.close()


def test_fixed_acceptance_fallback_checked_without_specifier(tmp_path):
    feature, brain, _ = _feature(tmp_path)
    tid = _enqueue(feature, brain, {FIXED_ACCEPTANCE: ["report.md exists"]})
    prompts = []

    async def query(_cli, prompt):
        prompts.append(prompt)
        return '{"pass": false, "missing": "report.md missing"}', "", []

    feature._query = query
    _run(feature, feature._execute(feature.store.get_task(tid)))
    assert prompts and "report.md exists" in prompts[0]
    prompts.clear()

    t = _run_once(feature, tid, _exec("Done."))
    assert prompts and "report.md exists" in prompts[0]
    assert t["status"] == "ready" and t["metadata"]["acceptance_fixes"] == 1

    tid_v = _enqueue(feature, brain, needs_approval=True)
    assert feature.store.claim(tid_v, "w")
    feature.store.complete(
        tid_v, "w", "Wrote report.md.", needs_approval=True,
        metadata={FIXED_ACCEPTANCE: ["report.md exists"], "acceptance_check": "unverified"},
    )
    prompts.clear()

    async def verify_pass(_cli, prompt):
        prompts.append(prompt)
        return '{"pass": true, "missing": ""}', "", []

    async def run_verify():
        res = await feature.verify(tid_v, brain=brain)
        if feature._verify_jobs:
            await asyncio.gather(*list(feature._verify_jobs))
        return res

    feature._query = verify_pass
    res = _run(feature, run_verify())
    assert res["ok"] and res["started"]
    assert prompts and "report.md exists" in prompts[0]
    verified = feature.store.get_task(tid_v)
    assert verified["status"] == "review" and verified["metadata"]["acceptance_check"] == "ai"
    feature.store.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
