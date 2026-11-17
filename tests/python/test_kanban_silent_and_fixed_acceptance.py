"""Kanban jobs: the [SILENT] flag (issue 1483) and done-criteria handed in with the job (issue 1481).

- 1483: reminders and webhooks finish quietly when the answer opens or ends with [SILENT]; a Kanban job used to push
  "[SILENT]" to the chat and the bell on every run, and the acceptance check could fail it as empty.
- 1481: a job queued by a script with fixed wording had its intent rewritten and its done-criteria invented by the
  specifier on every run, so the same job passed one day and stuck at acceptance_failed the next.

    python tests/python/test_kanban_silent_and_fixed_acceptance.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import sys

import pytest

from tasks import FIXED_ACCEPTANCE, TasksDeps, TasksFeature


async def _no_workflow(*_a, **_k):
    if False:
        yield {}


def _feature(tmp_path, reports):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)

    async def report(*a, **k):
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
    return TasksFeature(deps), brain


def _run_once(feature, tid):
    async def go():
        assert await feature._claim_and_spawn(tid)
        await feature._workers[tid]
        return feature.store.get_task(tid)
    return asyncio.run(go())


@pytest.mark.parametrize("answer", ["[SILENT]", "Checked 12 orders, nothing new.\n[SILENT]", "**[SILENT]** no change"])
def test_silent_job_is_done_without_a_report_or_an_acceptance_check(tmp_path, answer):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    checked = []

    async def execute(task):
        return answer, "", False, {}

    async def check(task, result):
        checked.append(result)
        return False, "empty answer", "ai"

    feature._execute = execute
    feature._check_acceptance = check
    root = feature._ensure(str(brain))
    tid = feature.store.enqueue(root, "Twice-daily check", "Look for new orders", capability="files", status="ready")
    t = _run_once(feature, tid)
    assert t["status"] == "done", (t["status"], t.get("block_reason"))
    assert t["metadata"].get("silent") is True and t["metadata"].get("acceptance_check") == "silent"
    assert not checked, "a [SILENT] answer must not go through the acceptance check"
    assert not reports, "a [SILENT] answer must not reach the chat or the bell"


def test_a_real_answer_still_reports(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)

    async def execute(task):
        return "Two new orders: #12 and #13. Mentioning [SILENT] in the middle does not count.", "", False, {}

    async def check(task, result):
        return True, "", "ai"

    feature._execute = execute
    feature._check_acceptance = check
    root = feature._ensure(str(brain))
    tid = feature.store.enqueue(root, "Order check", "Look for new orders", capability="files", status="ready")
    t = _run_once(feature, tid)
    assert t["status"] == "done" and not t["metadata"].get("silent")
    assert reports, "a real result is still sent"


def test_fixed_acceptance_survives_the_specifier(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    intent = "Export yesterday's orders to exports/orders.csv. Do not touch anything else."
    fixed = ["exports/orders.csv exists", "The answer gives the number of orders"]

    async def specify(task):
        return {"intent": "REWRITTEN: also make a chart and email it", "capability": "files",
                "execution_mode": "auto", "acceptance": ["A chart PNG exists", "An email was sent"]}, ""

    feature._specify = specify
    tid = feature.enqueue(str(brain), "Nightly export", intent, acceptance=fixed)
    t = feature.store.get_task(tid)
    assert t["metadata"].get(FIXED_ACCEPTANCE) == fixed, "the criteria are stored with the job"
    t = _run_once(feature, tid)
    assert t["intent"] == intent, "the intent is kept word for word"
    assert t["metadata"].get("acceptance") == fixed, "the check reads the handed-in criteria, not invented ones"
    assert t["capability"] == "files", "the specifier still picks the lane"


def test_without_fixed_acceptance_the_specifier_still_writes_them(tmp_path):
    feature, brain = _feature(tmp_path, [])

    async def specify(task):
        return {"intent": "Clear intent", "capability": "files", "execution_mode": "auto",
                "acceptance": ["Some file exists"]}, ""

    feature._specify = specify
    tid = feature.enqueue(str(brain), "Loose job", "do the thing")
    t = _run_once(feature, tid)
    assert t["intent"] == "Clear intent" and t["metadata"].get("acceptance") == ["Some file exists"]


def _javis_task_plugin():
    path = ROOT / "system" / "plugins" / "javis-task" / "plugin.py"
    spec = importlib.util.spec_from_file_location("javis_task_plugin_1481", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_javis_task_passes_acceptance_through(tmp_path, monkeypatch):
    plugin = _javis_task_plugin()
    seen = {}

    class FakeFeature:
        store = type("S", (), {"get_task": staticmethod(lambda tid: {})})()

        def enqueue(self, *a, **k):
            seen["args"], seen["kwargs"] = a, k
            return "t_1"

        def board_view(self, root):
            return {"orchestration": "auto"}

        def workflow_catalog(self, root):
            return []

    monkeypatch.setattr(plugin.tasks_mod, "current", lambda: FakeFeature())
    monkeypatch.setattr(plugin, "_workflows", lambda f, root: {})
    ctx = type("C", (), {"vault_root": str(tmp_path)})()
    out = plugin._them({"title": "Nightly export", "intent": "x", "chat_id": "web:1",
                        "acceptance": ["exports/orders.csv exists", "  ", "count given"]}, ctx)
    assert seen["kwargs"].get("acceptance") == ["exports/orders.csv exists", "count given"], seen
    assert "Fixed done-criteria: 2" in out
    out = plugin._them({"title": "Other", "intent": "x", "chat_id": "web:1", "acceptance": "a\nb\n"}, ctx)
    assert seen["kwargs"].get("acceptance") == ["a", "b"], "one criterion per line also works"
    plugin._them({"title": "Plain", "intent": "x", "chat_id": "web:1"}, ctx)
    assert "acceptance" not in seen["kwargs"], "no criteria, no change to the call"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
