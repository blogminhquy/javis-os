"""A failed acceptance check goes back to the worker first, then to the owner as two buttons (2026-11-08).

    python -m pytest tests/python/test_kanban_acceptance_fix_round.py

Owner report: a background job whose result failed the acceptance check landed in "Background job needs your
answer" with a reply box, but the card held no question, only the checker's reason ("section X is numbered
wrong"). The owner had nothing to answer: the worker missed a criterion. Now the first miss returns the job to its
worker with the reason, a second miss waits for the owner as `acceptance_failed` with "Fix and run again" and
"Accept as is".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json

import task_store as ts_mod
from task_store import ACCEPTANCE_FAILED, TaskStore
from tasks import TasksDeps, TasksFeature


async def _no_workflow(*_a, **_k):
    if False:
        yield {}


def _feature(tmp_path, reports=None):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)

    async def report(*a, **k):
        if reports is not None:
            reports.append((a, k))
        return True

    deps = TasksDeps(
        brain_root=lambda b: str(brain),
        atomic_write_text=lambda p, t: None,
        execute_workflow=_no_workflow,
        workflows_dir=lambda b: brain / "workflows",
        build_system_prompt=lambda b: "",
        aux_model=lambda: None,
        safe_tools=["Read", "Write", "Edit", "Glob", "Grep", "LS"],
        state_dir=tmp_path / "state",
        report=report,
    )
    return TasksFeature(deps), str(brain)


def _enqueue(feature, brain, acceptance=None, max_attempts=None, needs_approval=False):
    root = feature._ensure(brain)
    kw = {"max_attempts": max_attempts} if max_attempts else {}
    tid = feature.store.enqueue(root, "Report", "write report.md", capability="files", status="ready",
                                needs_approval=needs_approval, dedupe_title=False, **kw)
    if acceptance:
        with feature.store._lock:
            feature.store._db.execute("UPDATE tasks SET metadata_json=? WHERE id=?",
                                      (json.dumps({"acceptance": acceptance}), tid))
            feature.store._db.commit()
    return tid


def _verdicts(feature, verdicts):
    """The checker answers each run with the next verdict in the list."""
    feature._base_cli = lambda *a, **k: object()
    left = list(verdicts)

    async def query(cli, prompt):
        return json.dumps(left.pop(0)), "", []
    feature._query = query


def _run_once(feature, tid, execute):
    feature._execute = execute

    async def go():
        assert await feature._claim_and_spawn(tid)
        await feature._workers[tid]
        for hen in list(feature._hen_bao.values()):
            hen.cancel()
        return feature.store.get_task(tid)
    return asyncio.run(go())


def test_first_miss_goes_back_to_the_worker_with_the_reason(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    tid = _enqueue(feature, brain, ["Sections are numbered 1 to 5"], max_attempts=1)
    _verdicts(feature, [{"pass": False, "missing": "Section 3 is numbered 4"}])
    seen = []

    async def execute(task):
        seen.append(TasksFeature._hoi_dap(task))
        return "Wrote report.md.", "", False, {}

    t = _run_once(feature, tid, execute)
    assert t["status"] == "ready", t["status"]
    assert t["block_kind"] == "" and t["attempts"] == 0
    last = t["metadata"]["qa"][-1]
    assert last["kind"] == "acceptance_fix" and "Section 3 is numbered 4" in last["q"]
    assert t["metadata"]["acceptance_fixes"] == 1
    # Nothing goes to the owner on the first miss.
    assert not reports
    # The next run reads the checker's reason and the last report.
    block = TasksFeature._hoi_dap(t)
    assert "CHƯA ĐẠT" in block and "Section 3 is numbered 4" in block and "Wrote report.md" in block


def test_second_miss_waits_for_the_owner_without_a_question(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    tid = _enqueue(feature, brain, ["Sections are numbered 1 to 5"], max_attempts=1)
    _verdicts(feature, [{"pass": False, "missing": "Section 3 is numbered 4"},
                        {"pass": False, "missing": "Section 5 is missing"}])

    async def execute(task):
        return "Wrote report.md.", "", False, {}

    assert _run_once(feature, tid, execute)["status"] == "ready"
    t = _run_once(feature, tid, execute)
    assert t["status"] == "blocked" and t["block_kind"] == ACCEPTANCE_FAILED, (t["status"], t["block_kind"])
    assert t["block_reason"] == "Section 5 is missing"
    assert t["metadata"]["acceptance_check"] == "failed"
    # Not a question: no reply box, no "needs your answer" message.
    assert TasksFeature._cau_hoi_dang_cho(t) == ""
    assert TaskStore.waits_for_owner(t)
    assert len(reports) == 1
    a, k = reports[0]
    assert k["viec"]["status"] == "kiem" and "Section 5 is missing" in a[1]


def test_a_pass_after_the_fix_round_is_done(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _enqueue(feature, brain, ["report.md exists"])
    _verdicts(feature, [{"pass": False, "missing": "no report.md"}, {"pass": True, "missing": ""}])

    async def execute(task):
        return "Wrote report.md.", "", False, {}

    _run_once(feature, tid, execute)
    t = _run_once(feature, tid, execute)
    assert t["status"] == "done" and t["metadata"]["acceptance_check"] == "ai"


def test_a_worker_that_says_it_could_not_finish_goes_straight_to_the_owner(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _enqueue(feature, brain)

    async def execute(task):
        return "Chạy thử chưa xong. 3 bước ảnh không chạy được vì thiếu công cụ ảnh.", "", False, {}

    t = _run_once(feature, tid, execute)
    assert t["status"] == "blocked" and t["block_kind"] == ACCEPTANCE_FAILED
    assert "chưa xong" in t["block_reason"]


def _failed_job(feature, brain, needs_approval=False):
    tid = _enqueue(feature, brain, ["a"], needs_approval=needs_approval)
    s = feature.store
    assert s.claim(tid, "w")
    meta = {"acceptance": ["a"], "acceptance_fixes": 1}
    got = s.acceptance_failed(tid, "w", "Only 2 sections", result="Wrote a.md", metadata=meta,
                              needs_approval=needs_approval)
    assert got["block_kind"] == ACCEPTANCE_FAILED
    return tid


def test_owner_fix_sends_it_back_with_fresh_attempts(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _failed_job(feature, brain)
    r = asyncio.run(feature.resolve_acceptance(tid, "fix", brain=brain))
    assert r["ok"] and r["status"] == "ready", r
    t = feature.store.get_task(tid)
    assert t["attempts"] == 0 and t["block_kind"] == ""
    assert t["metadata"]["qa"][-1]["kind"] == "acceptance_fix" and "Only 2 sections" in t["metadata"]["qa"][-1]["q"]
    # The automatic round is used up: a further miss goes straight back to the owner.
    assert t["metadata"]["acceptance_fixes"] == 1
    assert "acceptance_check" not in t["metadata"]


def test_owner_accept_closes_it_as_done_or_back_to_review(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _failed_job(feature, brain)
    r = asyncio.run(feature.resolve_acceptance(tid, "accept", brain=brain))
    assert r["ok"] and r["status"] == "done", r
    t = feature.store.get_task(tid)
    assert t["metadata"]["acceptance_check"] == "accepted" and t["result"] == "Wrote a.md"

    rid = _failed_job(feature, brain, needs_approval=True)
    assert asyncio.run(feature.resolve_acceptance(rid, "accept", brain=brain))["status"] == "review"


def test_resolve_refuses_other_jobs_and_unknown_choices(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _failed_job(feature, brain)
    assert not asyncio.run(feature.resolve_acceptance(tid, "maybe", brain=brain))["ok"]
    other = _enqueue(feature, brain)
    assert not asyncio.run(feature.resolve_acceptance(other, "accept", brain=brain))["ok"]
    assert feature.store.get_task(other)["status"] == "ready"


def test_a_followup_gives_the_job_a_new_fix_round(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _failed_job(feature, brain)
    assert asyncio.run(feature.followup(tid, "Use 5 sections", brain=brain))["ok"]
    meta = feature.store.get_task(tid)["metadata"]
    assert "acceptance_fixes" not in meta and "acceptance_check" not in meta


def test_old_question_cards_move_to_the_new_state_on_start(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _enqueue(feature, brain)
    s = feature.store
    assert s.claim(tid, "w")
    s.ask(tid, "w", "Chưa đạt điều kiện hoàn thành: phần X đánh số chưa khớp")
    real = _enqueue(feature, brain)
    real_q = "Bạn muốn gửi cho nhóm nào?"
    assert s.claim(real, "w2")
    s.ask(real, "w2", real_q)
    path = s.path
    s.close()
    again = TaskStore(path)
    assert again.get_task(tid)["block_kind"] == ACCEPTANCE_FAILED
    assert again.get_task(real)["block_kind"] == "needs_input"
    again.close()


def test_route_and_dashboard_are_wired():
    src = (SERVER / "tasks.py").read_text(encoding="utf-8")
    assert '"/kanban/task/acceptance"' in src
    js = (ROOT / "dashboard" / "tasks.js").read_text(encoding="utf-8")
    assert 'k === "acceptance_failed"' in js and "/kanban/task/acceptance" in js
    assert 'data-act="accfix"' in js and 'data-act="accok"' in js
    for lang in ("vi", "en"):
        d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for k in ("viec.st_kiem", "nv.acc.cap", "nv.a.accfix", "nv.a.accok", "nv.ok.accfix", "nv.ok.accok"):
            assert d.get(k), (lang, k)
    assert ts_mod.ACCEPTANCE_AUTO_FIXES == 1



def _plugin():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "javis_task_plugin_acceptance", ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_chat_tool_accepts_or_fixes_a_failed_job(tmp_path, monkeypatch):
    # The owner can pick right where the notice landed (Telegram, Zalo, web chat), not only on the Tasks page.
    import tasks as tasks_mod
    feature, brain = _feature(tmp_path)
    monkeypatch.setattr(tasks_mod, "current", lambda: feature)
    m = _plugin()

    class Ctx:
        vault_root = brain

    assert "Không có việc nào" in asyncio.run(m._chay({"op": "accept"}, Ctx()))
    a = _failed_job(feature, brain)
    listed = asyncio.run(m._chay({"op": "list"}, Ctx()))
    assert "MÁY TỰ KIỂM CHƯA QUA" in listed and "Only 2 sections" in listed

    # Exactly one job waiting: no id needed.
    out = asyncio.run(m._chay({"op": "accept"}, Ctx()))
    assert out.startswith("Đã chấp nhận kết quả của việc " + a), out
    assert feature.store.get_task(a)["status"] == "done"

    # Two waiting: never guess, list them so the model asks back.
    b, c = _failed_job(feature, brain), _failed_job(feature, brain)
    out = asyncio.run(m._chay({"op": "fix"}, Ctx()))
    assert out.startswith("ERROR") and b in out and c in out
    out = asyncio.run(m._chay({"op": "fix", "id": b}, Ctx()))
    assert out.startswith("Đã trả việc " + b), out
    assert feature.store.get_task(b)["status"] == "ready" and feature.store.get_task(c)["status"] == "blocked"
    # A job that is not waiting for a pick is refused.
    assert asyncio.run(m._chay({"op": "accept", "id": a}, Ctx())).startswith("ERROR")


def test_failed_check_notice_says_the_pick_can_be_made_in_chat(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    tid = _failed_job(feature, brain)
    asyncio.run(feature._report(feature.store.get_task(tid)))
    text = reports[-1][0][1]
    assert "chấp nhận" in text and "sửa lại" in text and tid in text


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("skipped: pytest is not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
