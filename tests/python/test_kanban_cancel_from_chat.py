"""Cancel a Kanban job from chat, the same way the Tasks page does (issue 1426).

    python tests/run.py kanban_cancel_from_chat

Before this the chat tool `javis_task` could queue, answer, accept and fix work but not cancel it, so the owner had to
open the Tasks page. Pinned here: op=cancel goes through the same `TasksFeature.cancel` as the page's button (a running
job has its worker stopped, any other job moves to cancelled), the owner's reason lands in the job's log, an unknown
id, a job of another brain and a job that already ended are refused, and the tool is gated exactly like op=fix.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-cancel-"))

import plugins_host  # noqa: E402
import tasks as tasks_mod  # noqa: E402
import turn_context  # noqa: E402
from tasks import TasksDeps, TasksFeature  # noqa: E402


async def _no_workflow(*_a, **_k):
    if False:
        yield {}


async def _report(*_a, **_k):
    return True


def _feature(tmp_path):
    brain = tmp_path / "brain"
    other = tmp_path / "other"
    brain.mkdir(exist_ok=True)
    other.mkdir(exist_ok=True)
    deps = TasksDeps(
        # A real folder is its own brain; anything else ("brain", "") is the default one, like main._brain_root.
        brain_root=lambda b: b if b and Path(b).is_dir() else str(brain),
        atomic_write_text=lambda p, t: None,
        execute_workflow=_no_workflow,
        workflows_dir=lambda b: Path(b) / "workflows",
        build_system_prompt=lambda b: "",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=tmp_path / "state",
        report=_report,
    )
    return TasksFeature(deps), str(brain), str(other)


def _queued(feature, brain, title="Report"):
    return feature.store.enqueue(feature._ensure(brain), title, "write report.md", capability="files",
                                 status="ready", dedupe_title=False)


def _log(feature, tid):
    return [(e["event_type"], e["message"]) for e in feature.store.list_events(tid, 50)]


def _plugin():
    spec = importlib.util.spec_from_file_location(
        "javis_task_plugin_cancel", ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ctx(vault):
    class Ctx:
        vault_root = vault
    return Ctx()


# ---------------------------------------------------------------- the shared service

def test_cancel_moves_a_queued_job_and_logs_the_reason(tmp_path):
    feature, brain, _ = _feature(tmp_path)
    tid = _queued(feature, brain)
    r = asyncio.run(feature.cancel(tid, brain=brain, reason="plans changed", by="chat"))
    assert r == {"ok": True, "cancelled": True, "stopped": False}, r
    assert feature.store.get_task(tid)["status"] == "cancelled"
    assert ("operator_move", "ready -> cancelled: operator cancel (chat): plans changed") in _log(feature, tid)


def test_the_page_button_keeps_its_exact_log_line(tmp_path):
    feature, brain, _ = _feature(tmp_path)
    tid = _queued(feature, brain)
    assert asyncio.run(feature.cancel(tid, brain="brain"))["ok"]
    assert ("operator_move", "ready -> cancelled: operator cancel") in _log(feature, tid)


def test_cancel_refuses_unknown_other_brain_and_finished_jobs(tmp_path):
    feature, brain, other = _feature(tmp_path)
    r = asyncio.run(feature.cancel("nope", brain=brain))
    assert not r["ok"] and r["code"] == "not_found"

    theirs = _queued(feature, other)
    r = asyncio.run(feature.cancel(theirs, brain=brain))
    assert not r["ok"] and r["code"] == "not_found"
    assert feature.store.get_task(theirs)["status"] == "ready"

    for final in ("done", "cancelled", "archived"):
        tid = _queued(feature, brain, f"Finished {final}")
        assert feature.store.move(tid, final)
        r = asyncio.run(feature.cancel(tid, brain=brain))
        assert not r["ok"] and r["code"] == "finished" and r["status"] == final, r
        # A finished result is never turned into "cancelled" (an archived job would come back on the board).
        assert feature.store.get_task(tid)["status"] == final


def test_page_route_goes_through_the_shared_cancel(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    feature, brain, _ = _feature(tmp_path)
    app = FastAPI()
    app.include_router(feature.router)
    client = TestClient(app)
    tid = _queued(feature, brain)
    assert client.post("/kanban/task/cancel", data={"id": tid, "brain": "brain"}).json()["ok"]
    assert feature.store.get_task(tid)["status"] == "cancelled"
    done = client.post("/kanban/task/cancel", data={"id": tid, "brain": "brain"}).json()
    assert done["ok"] is False and done["error"]

    calls = []

    async def spy(task_id, brain="", reason="", by="owner"):
        calls.append((task_id, brain, reason, by))
        return {"ok": True, "cancelled": True, "stopped": False}

    feature.cancel = spy
    client.post("/kanban/task/cancel", data={"id": "k1", "brain": ""})
    assert calls == [("k1", "brain", "", "owner")], calls


# ---------------------------------------------------------------- the chat tool

def test_chat_tool_cancels_a_queued_job(tmp_path, monkeypatch):
    feature, brain, other = _feature(tmp_path)
    monkeypatch.setattr(tasks_mod, "current", lambda: feature)
    m = _plugin()
    tid = _queued(feature, brain)

    out = asyncio.run(m._chay({"op": "cancel"}, _ctx(brain)))
    assert out.startswith("ERROR") and "op=list" in out, out
    assert feature.store.get_task(tid)["status"] == "ready"

    out = asyncio.run(m._chay({"op": "cancel", "id": tid, "reason": "khách đổi ý"}, _ctx(brain)))
    assert out.startswith("Đã huỷ việc " + tid), out
    assert feature.store.get_task(tid)["status"] == "cancelled"
    assert any("operator cancel (chat): khách đổi ý" in msg for _ev, msg in _log(feature, tid))

    out = asyncio.run(m._chay({"op": "cancel", "id": tid}, _ctx(brain)))
    assert out.startswith("ERROR") and "đã kết thúc" in out, out

    out = asyncio.run(m._chay({"op": "cancel", "id": "khong-co"}, _ctx(brain)))
    assert out.startswith("ERROR") and "không có việc khong-co" in out, out

    theirs = _queued(feature, other)
    out = asyncio.run(m._chay({"op": "cancel", "id": theirs}, _ctx(brain)))
    assert out.startswith("ERROR") and feature.store.get_task(theirs)["status"] == "ready", out

    out = asyncio.run(m._chay({"op": "cancel", "id": tid}, _ctx("")))
    assert out.startswith("ERROR") and "brain" in out


def test_chat_tool_stops_a_running_job_with_the_reason(tmp_path, monkeypatch):
    feature, brain, _ = _feature(tmp_path)
    monkeypatch.setattr(tasks_mod, "current", lambda: feature)
    m = _plugin()
    tid = _queued(feature, brain)

    async def go():
        started = asyncio.Event()

        async def execute(task):
            started.set()
            await asyncio.sleep(60)
            return "never", "", False, {}

        feature._execute = execute
        assert await feature._claim_and_spawn(tid)
        worker = feature._workers[tid]
        await asyncio.wait_for(started.wait(), 5)
        out = await m._chay({"op": "cancel", "id": tid, "reason": "too slow"}, _ctx(brain))
        await asyncio.gather(worker, return_exceptions=True)
        return out

    out = asyncio.run(go())
    assert out.startswith("Đã dừng và huỷ việc " + tid), out
    t = feature.store.get_task(tid)
    assert t["status"] == "cancelled" and t["block_reason"] == "worker cancelled (chat): too slow", t["block_reason"]
    assert ("cancelled", "worker cancelled (chat): too slow") in _log(feature, tid)
    assert not feature._cancel_reasons


# ---------------------------------------------------------------- permission levels

def test_cancel_is_gated_exactly_like_fix():
    ran = []

    def handler(args, ctx):
        ran.append(args.get("op"))
        return "ran"

    tool = {"handler": handler, "min_mode": "safe", "name": "javis_task"}

    def outcome(op, mode, bot=False):
        tok = None
        if bot:
            turn = turn_context.make("telegram", sender_id="u1", chat_id="c1", la_chu=False)
            turn["bot_id"] = "bot_abc"
            tok = turn_context.bind(turn)
        try:
            del ran[:]
            res = asyncio.run(plugins_host._make_call(tool, None, mode)({"op": op, "id": "k1"}))
            return res.startswith("ERROR") or res != "ran", bool(ran)
        finally:
            if tok is not None:
                turn_context.reset(tok)

    for mode in ("full", "auto", "suggest", "gated"):
        for bot in (False, True):
            assert outcome("cancel", mode, bot) == outcome("fix", mode, bot), (mode, bot)
    # The levels themselves: the owner at full or auto may cancel; read-only, an ungated Team step and a customer bot
    # below full may not.
    assert outcome("cancel", "full") == (False, True)
    assert outcome("cancel", "auto") == (False, True)
    assert outcome("cancel", "suggest") == (True, False) and outcome("cancel", "gated") == (True, False)
    assert outcome("cancel", "auto", bot=True) == (True, False)
    assert outcome("cancel", "full", bot=True) == (False, True)
    # Nothing to cap: cancel passes no level on to later work.
    assert plugins_host._cap_job_level("javis_task", {"op": "cancel", "id": "k1"}, "auto") == (
        {"op": "cancel", "id": "k1"}, "")


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("skipped: pytest is not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
