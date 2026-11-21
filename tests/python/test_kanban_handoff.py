"""Kanban: steps only the owner can do go to "Left for you" instead of failing the job forever.

Field report 2026-11-21 (server on 0.408, root cause still on main at 0.617.1): the specifier wrote done-criteria no
worker can meet ("uploaded to Drive" for a 67.8 MB file past the hub's 10 MB cap, "92 voice lines listened to",
"DeepSeek's proof pass is in" which is another job's step). Four finished jobs failed the check on every run, each
burning a fix run and calling the owner. Now:

- the specifier is told what the worker can reach and splits `acceptance` from a new `handoff` list;
- the worker is told the handoff steps are not its job;
- the checker can pass a job whose only misses are out of the worker's reach (and explained), moving them to handoff;
- the card and the chat report show "Left for you".

    python tests/python/test_kanban_handoff.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json

import aux_engine
from tasks import HANDOFF, TasksDeps, TasksFeature, clean_lines, merge_handoff


async def _no_workflow(*_a, **_k):
    if False:
        yield {}


def _feature(tmp_path, reports=None):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    reports = reports if reports is not None else []

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


class _Cli:
    def __init__(self, out):
        self.out = out
        self.disallowed_tools = None

    def is_available(self):
        return True

    async def query(self, _prompt):
        yield {"type": "final", "content": self.out}


def _with_model(feature, monkeypatch, out, seen):
    monkeypatch.setattr(aux_engine, "read_spec", lambda *a, **k: {"provider": "deepseek"})
    feature._base_cli = lambda *a, **k: _Cli(out)
    orig = feature._query

    async def query(cli, prompt):
        seen.append(prompt)
        return await orig(cli, prompt)

    feature._query = query


def _run_once(feature, tid):
    async def go():
        assert await feature._claim_and_spawn(tid)
        await feature._workers[tid]
        return feature.store.get_task(tid)
    return asyncio.run(go())


def test_clean_lines_and_merge():
    assert clean_lines("not a list") == []
    assert clean_lines(["  a  ", "", "a", {"x": 1}, "b\n c"]) == ["a", "b c"]
    assert merge_handoff(["a"], ["a", "b"]) == ["a", "b"]
    assert len(clean_lines([str(i) for i in range(50)])) == 10


def test_specifier_is_told_what_the_worker_can_reach_and_returns_handoff(tmp_path, monkeypatch):
    feature, brain = _feature(tmp_path)
    seen = []
    out = json.dumps({"intent": "Make the deck", "capability": "files", "execution_mode": "auto",
                      "acceptance": ["exports/deck.pptx exists"],
                      "handoff": ["Upload exports/deck.pptx (67.8 MB) to the Drive folder", "Listen to the 92 lines"]})
    _with_model(feature, monkeypatch, out, seen)
    root = feature._ensure(str(brain))
    task = {"id": "t1", "brain_root": root, "title": "Deck", "intent": "make the deck and upload it",
            "idempotency_key": "", "execution_mode": "auto"}
    spec, err = asyncio.run(feature._specify(task))
    assert not err
    assert spec["acceptance"] == ["exports/deck.pptx exists"]
    assert spec[HANDOFF] == ["Upload exports/deck.pptx (67.8 MB) to the Drive folder", "Listen to the 92 lines"]
    prompt = seen[0]
    assert "Engine: deepseek" in prompt and "Shell (Bash): no" in prompt, "engine and shell are in the prompt"
    assert '"handoff"' in prompt and "Never put such a step in acceptance" in prompt


def test_handoff_reaches_the_job_metadata_and_the_worker_prompt(tmp_path, monkeypatch):
    feature, brain = _feature(tmp_path)

    async def specify(task):
        return {"intent": "Make the deck", "capability": "files", "execution_mode": "auto",
                "acceptance": ["exports/deck.pptx exists"], HANDOFF: ["Listen to the 92 lines"]}, ""

    feature._specify = specify
    tid = feature.enqueue(str(brain), "Deck", "make the deck")
    t = _run_once(feature, tid)
    assert t["metadata"].get(HANDOFF) == ["Listen to the 92 lines"]

    seen = []
    _with_model(feature, monkeypatch, "Done: exports/deck.pptx", seen)
    asyncio.run(feature._execute(t))
    assert "LEFT FOR THE OWNER" in seen[0] and "Listen to the 92 lines" in seen[0]
    assert TasksFeature._card(t)["metadata"].get(HANDOFF) == ["Listen to the 92 lines"], "the card gets the list"


def _check(tmp_path, monkeypatch, verdict):
    feature, brain = _feature(tmp_path)
    seen = []
    _with_model(feature, monkeypatch, json.dumps(verdict), seen)
    task = {"id": "t1", "brain_root": str(brain), "intent": "make the deck and upload it",
            "metadata": {"acceptance": ["deck exists", "uploaded to Drive"]}}
    return asyncio.run(feature._check_acceptance(task, "Deck at exports/deck.pptx. Upload: 67.8 MB is over the 10 MB cap.")), seen


def test_checker_passes_when_only_out_of_reach_steps_are_left(tmp_path, monkeypatch):
    (passed, why, how), seen = _check(tmp_path, monkeypatch, {
        "pass": False, "missing": "not uploaded", "owner_only": True,
        "handoff": ["Upload exports/deck.pptx (67.8 MB) to Drive: over the 10 MB tool cap"]})
    assert (passed, how) == (True, "ai")
    assert why == "Upload exports/deck.pptx (67.8 MB) to Drive: over the 10 MB tool cap"
    assert "owner_only" in seen[0] and "WHAT THE WORKER COULD REACH" in seen[0]


def test_checker_still_fails_real_misses(tmp_path, monkeypatch):
    (passed, why, how), _ = _check(tmp_path / "a", monkeypatch, {
        "pass": False, "missing": "deck missing", "owner_only": False, "handoff": ["x"]})
    assert (passed, why, how) == (False, "deck missing", "ai")
    # owner_only without saying what is left is not enough
    (passed, why, how), _ = _check(tmp_path / "b", monkeypatch, {
        "pass": False, "missing": "not uploaded", "owner_only": True, "handoff": []})
    assert (passed, how) == (False, "ai")
    (passed, why, how), _ = _check(tmp_path / "c", monkeypatch, {"pass": True, "missing": "nothing"})
    assert (passed, why, how) == (True, "", "ai")


def test_a_job_passed_with_handoff_is_done_and_rings_with_left_for_you(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)

    async def execute(task):
        return "Deck at exports/deck.pptx. Upload blocked: 67.8 MB is over the 10 MB cap.", "", False, {}

    async def check(task, result):
        return True, "Upload exports/deck.pptx to Drive", "ai"

    feature._execute = execute
    feature._check_acceptance = check
    root = feature._ensure(str(brain))
    tid = feature.store.enqueue(root, "Deck", "make the deck", capability="files", status="ready",
                                metadata={"acceptance": ["deck exists"], HANDOFF: ["Listen to the 92 lines"]})
    t = _run_once(feature, tid)
    assert t["status"] == "done", (t["status"], t.get("block_reason"))
    assert t["metadata"][HANDOFF] == ["Listen to the 92 lines", "Upload exports/deck.pptx to Drive"]
    (args, kwargs), = reports
    assert "Upload exports/deck.pptx to Drive" in args[1]
    assert kwargs.get("quiet") is False, "a done job that leaves steps for the owner is not reported silently"


def test_recheck_stores_handoff(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(str(brain))
    tid = feature.store.enqueue(root, "Deck", "make the deck", capability="files", status="ready",
                                metadata={"acceptance": ["deck exists"]})
    feature.store._db.execute("UPDATE tasks SET status='done' WHERE id=?", (tid,))
    feature.store._db.commit()
    t = feature.store.set_acceptance(tid, "ai", "x", handoff=["Upload the deck"])
    assert t["metadata"][HANDOFF] == ["Upload the deck"] and t["status"] == "done"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
