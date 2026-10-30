"""Work page upgrade (0.411.0): a lighter board, follow-up notes, checking a job again, repeat-job hints,
routing a job to an assistant and running small jobs light.

    python tests/python/test_kanban_work_page_0411.py

Owner, 30/10/2026: the Work page was "not very useful and often broken". The audit found the board shipped every
job's full report every 3 seconds, showed the OLDEST finished jobs as History, and hid new jobs once 500 old ones
piled up; a stopped or finished job could only be retried unchanged.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI

import aux_engine
from task_store import TaskStore
from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


async def _report(*_a, **_k):
    return True


def _feature(tmp_path, roster=None, persona=None):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    deps = TasksDeps(
        brain_root=lambda v: str(brain),
        atomic_write_text=_atomic,
        execute_workflow=_workflow,
        workflows_dir=lambda b: Path(brain) / "workflows",
        build_system_prompt=lambda b: "system",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)],
        report=_report,
        agent_roster=roster,
        agent_persona=persona,
    )
    FastAPI()
    return TasksFeature(deps), str(brain)


def _finish(store, tid, status="done", result="ok", metadata=None):
    """Put a job straight into a final state, the way a worker leaves it."""
    assert store.claim(tid, "w")
    if status == "done":
        return store.complete(tid, "w", result, metadata=metadata or {})
    return store.block(tid, "w", "transient", "boom", result=result)


# ---------------------------------------------------------------- board

def test_history_is_newest_first_and_new_jobs_are_never_hidden(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    old = []
    for i in range(25):
        tid = s.enqueue(root, f"old {i}", "x", capability="files", status="ready", dedupe_title=False)
        _finish(s, tid)
        old.append(tid)
    time.sleep(0.01)
    newest = s.enqueue(root, "newest done", "x", capability="files", status="ready")
    _finish(s, newest)
    fresh = s.enqueue(root, "fresh in queue", "x", capability="files", status="ready", priority=3)
    view = feature.board_view(brain)
    hist = view["operations"]["history"]
    assert hist[0]["id"] == newest, [h["title"] for h in hist[:3]]
    assert len(hist) == 20 and view["history_more"] is True
    assert view["counts"]["done"] == 26
    assert any(t["id"] == fresh for t in view["operations"]["queue"])
    more = feature.board_view(brain, history_limit=40)
    assert len(more["operations"]["history"]) == 26 and more["history_more"] is False
    s.close()


def test_open_jobs_are_not_crowded_out_by_old_finished_ones(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    lists_cap = 5
    for i in range(8):
        _finish(s, s.enqueue(root, f"done {i}", "x", capability="files", status="ready", priority=1,
                             dedupe_title=False))
    late = s.enqueue(root, "late low priority", "x", capability="files", status="ready", priority=3)
    got = s.board_lists(root, history_limit=3, cap=lists_cap)
    assert [t["id"] for t in got["open"]] == [late]
    s.close()


def test_card_is_slim_and_unchanged_board_answers_unchanged(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    tid = s.enqueue(root, "Long report", "x", capability="files", status="ready")
    _finish(s, tid, result="x" * 5000, metadata={"tool_calls": ["Read"] * 100, "acceptance": ["a"],
                                                 "acceptance_check": "ai"})
    view = feature.board_view(brain)
    card = view["operations"]["history"][0]
    assert len(card["result"]) == TasksFeature.CARD_RESULT_CHARS and card["result_more"] is True
    assert "tool_calls" not in card["metadata"] and card["metadata"]["acceptance_check"] == "ai"
    again = feature.board_view(brain, rev=view["rev"])
    assert again == {"schema": 2, "unchanged": True, "rev": view["rev"]}
    s.enqueue(root, "Another", "x", capability="files", status="ready")
    changed = feature.board_view(brain, rev=view["rev"])
    assert not changed.get("unchanged") and changed["rev"] != view["rev"]
    feature.store.set_orchestration(root, "auto")
    assert not feature.board_view(brain, rev=changed["rev"]).get("unchanged")
    s.close()


# ---------------------------------------------------------------- follow-up

def test_followup_on_a_done_job_requeues_it_with_the_note_and_last_report(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    tid = s.enqueue(root, "Article", "write it", capability="files", status="ready")
    _finish(s, tid, result="Wrote article.md with 3 paragraphs.",
            metadata={"acceptance": ["article.md exists"], "acceptance_check": "unverified"})
    r = asyncio.run(feature.followup(tid, "Make paragraph 2 shorter", brain=brain))
    assert r["ok"] and r["status"] == "ready", r
    t = s.get_task(tid)
    assert t["attempts"] == 0 and t["block_kind"] == ""
    last = t["metadata"]["qa"][-1]
    assert last["kind"] == "followup" and last["a"] == "Make paragraph 2 shorter"
    assert "3 paragraphs" in last["progress"]
    assert "acceptance_check" not in t["metadata"] and t["metadata"]["acceptance"] == ["article.md exists"]
    block = TasksFeature._hoi_dap(t)
    assert "Chủ dặn thêm" in block and "Make paragraph 2 shorter" in block and "3 paragraphs" in block
    s.close()


def test_followup_refuses_running_and_waiting_jobs(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    running = s.enqueue(root, "Running", "x", capability="files", status="ready")
    assert s.claim(running, "w")
    assert not asyncio.run(feature.followup(running, "note", brain=brain))["ok"]
    assert s.get_task(running)["status"] == "running"
    waiting = s.enqueue(root, "Waiting", "x", capability="files", status="ready")
    assert s.claim(waiting, "w2")
    s.ask(waiting, "w2", "Which file?")
    r = asyncio.run(feature.followup(waiting, "note", brain=brain))
    assert not r["ok"] and s.get_task(waiting)["block_kind"] == "needs_input"
    assert not asyncio.run(feature.followup(waiting, "   ", brain=brain))["ok"]
    s.close()


def test_followup_on_a_blocked_job_runs_it_again(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    tid = s.enqueue(root, "Broken", "x", capability="files", status="ready", max_attempts=1)
    _finish(s, tid, status="blocked")
    assert s.get_task(tid)["status"] == "blocked"
    assert asyncio.run(feature.followup(tid, "Use the other folder", brain=brain))["ok"]
    assert s.get_task(tid)["status"] == "ready"
    s.close()


# ---------------------------------------------------------------- check again

def _verify(feature, brain, tid, verdict):
    async def check(task, result):
        return verdict

    feature._check_acceptance = check

    async def go():
        r = await feature.verify(tid, brain=brain)
        for _ in range(50):
            if tid not in feature._verifying:
                break
            await asyncio.sleep(0.01)
        return r
    return asyncio.run(go())


def test_verify_marks_checked_or_sends_the_job_back_with_the_reason(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    meta = {"acceptance": ["file a.md has 3 sections"], "acceptance_check": "unverified"}
    ok_id = s.enqueue(root, "Good", "x", capability="files", status="ready")
    _finish(s, ok_id, metadata=dict(meta))
    assert _verify(feature, brain, ok_id, (True, "", "ai"))["started"]
    assert s.get_task(ok_id)["metadata"]["acceptance_check"] == "ai"
    assert s.get_task(ok_id)["status"] == "done"

    bad_id = s.enqueue(root, "Bad", "x", capability="files", status="ready")
    _finish(s, bad_id, metadata=dict(meta))
    _verify(feature, brain, bad_id, (False, "Only 2 sections in a.md", "ai"))
    t = s.get_task(bad_id)
    assert t["status"] == "blocked" and t["block_kind"] == "needs_input"
    assert "Only 2 sections" in t["block_reason"] and t["metadata"]["acceptance_check"] == "failed"
    # The reply box answers it like any question and the job runs again.
    got, err = s.answer(bad_id, "Add the missing section")
    assert got and got["status"] == "ready", err
    s.close()


def test_a_check_cut_short_by_a_restart_can_run_again(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    tid = s.enqueue(root, "Stuck", "x", capability="files", status="ready")
    _finish(s, tid, metadata={"acceptance": ["a"], "acceptance_check": "checking"})
    assert _verify(feature, brain, tid, (True, "", "ai"))["started"]
    assert s.get_task(tid)["metadata"]["acceptance_check"] == "ai"
    s.close()


def test_verify_needs_a_finished_job_with_criteria(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    queued = s.enqueue(root, "Queued", "x", capability="files", status="ready")
    assert not asyncio.run(feature.verify(queued, brain=brain))["ok"]
    bare = s.enqueue(root, "No criteria", "x", capability="files", status="ready")
    _finish(s, bare)
    assert not asyncio.run(feature.verify(bare, brain=brain))["ok"]
    s.close()


# ---------------------------------------------------------------- repeat-job hints

def test_a_job_asked_for_three_times_becomes_a_hint_until_dismissed(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    for day in ("28/10", "29/10", "30/10"):
        tid = s.enqueue(root, f"Báo cáo doanh thu ngày {day}", "Tổng hợp doanh thu POS", capability="files",
                        status="ready", created_by="chat")
        _finish(s, tid)
    for i in range(3):
        s.enqueue(root, f"Agent job {i} báo cáo doanh thu", "x", status="ready", created_by="agent:x",
                  dedupe_title=False)
    hints = feature.board_view(brain)["hints"]
    assert len(hints) == 1 and hints[0]["count"] == 3, hints
    assert "doanh thu" in hints[0]["title"]
    feature.store.dismiss_hint(root, hints[0]["key"])
    assert feature.board_view(brain)["hints"] == []
    s.close()


def test_two_similar_jobs_are_not_a_hint(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    for t in ("Viết bài Facebook về nước mắm", "Viết bài Facebook về nước mắm 2", "Dọn thư mục ảnh"):
        s.enqueue(root, t, "x", status="ready", created_by="user", dedupe_title=False)
    assert feature.board_view(brain)["hints"] == []
    s.close()


# ---------------------------------------------------------------- routing and light runs

class _SpecCli:
    def __init__(self, out):
        self.out = out

    def is_available(self):
        return True

    async def query(self, _prompt):
        yield {"type": "final", "content": self.out}


def _specify(tmp_path, monkeypatch, out, roster):
    seen = {}
    feature, brain = _feature(tmp_path, roster=lambda root: roster)
    monkeypatch.setattr(aux_engine, "read_spec", lambda *a, **k: {"provider": "anthropic-cli"})

    def base_cli(task, *a, **k):
        return _SpecCli(out)

    feature._base_cli = base_cli
    orig_query = feature._query

    async def query(cli, prompt):
        seen["prompt"] = prompt
        return await orig_query(cli, prompt)

    feature._query = query
    root = feature._ensure(brain)
    task = {"id": "t1", "brain_root": root, "title": "Viết email chào hàng", "intent": "viết email",
            "idempotency_key": ""}
    spec, err = asyncio.run(feature._specify(task))
    feature.store.close()
    return spec, seen.get("prompt", "")


ROSTER = [{"slug": "viet-email", "name": "Viết email", "role": "Viết email bán hàng", "key": "k1"}]


def test_specifier_routes_to_a_listed_assistant_only(tmp_path, monkeypatch):
    out = '{"intent":"x","capability":"files","execution_mode":"auto","acceptance":[],"effort":"normal","agent":"viet-email"}'
    spec, prompt = _specify(tmp_path, monkeypatch, out, ROSTER)
    assert spec["agent"] == {"slug": "viet-email", "name": "Viết email", "key": "k1"}
    assert "viet-email: Viết email (Viết email bán hàng)" in prompt
    out = '{"intent":"x","capability":"files","execution_mode":"auto","acceptance":[],"agent":"made-up"}'
    spec, _ = _specify(tmp_path / "b", monkeypatch, out, ROSTER)
    assert spec["agent"] is None


def test_light_effort_only_for_jobs_that_stay_in_the_brain(tmp_path, monkeypatch):
    out = '{"intent":"x","capability":"files","execution_mode":"auto","acceptance":[],"effort":"light"}'
    assert _specify(tmp_path, monkeypatch, out, [])[0]["effort"] == "light"
    out = '{"intent":"x","capability":"external-write","execution_mode":"auto","acceptance":[],"effort":"light"}'
    assert _specify(tmp_path / "b", monkeypatch, out, [])[0]["effort"] == "normal"
    out = '{"intent":"x","capability":"code","execution_mode":"auto","acceptance":[],"effort":"light"}'
    assert _specify(tmp_path / "c", monkeypatch, out, [])[0]["effort"] == "normal"


def test_lighten_only_lowers_effort():
    class Cli:
        pass
    for before, after in (("high", "low"), ("medium", "low"), ("low", "low"), ("off", "off"), (None, None)):
        c = Cli()
        if before is not None:
            c.effort = before
        TasksFeature._lighten(c)
        assert getattr(c, "effort", None) == after, (before, getattr(c, "effort", None))


def test_routed_job_runs_with_the_assistants_persona(tmp_path):
    calls = []

    def persona(root, slug, key):
        calls.append((slug, key))
        return "# VAI"

    feature, brain = _feature(tmp_path, persona=persona)
    root = feature._ensure(brain)
    task = {"brain_root": root, "idempotency_key": "",
            "metadata": {"agent": {"slug": "viet-email", "name": "Viết email", "key": "k1"}}}
    assert feature._persona(task, root) == "# VAI" and calls == [("viet-email", "k1")]
    assert feature._persona({"brain_root": root, "metadata": {}}, root) == ""
    feature.store.close()


def test_a_finished_run_records_how_long_it_took(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)

    async def execute(task):
        await asyncio.sleep(0.01)
        return "Done.", "", False, {}

    feature._execute = execute

    async def go():
        tid = feature.store.enqueue(root, "Quick", "x", capability="files", status="ready")
        assert await feature._claim_and_spawn(tid)
        await feature._workers[tid]
        return feature.store.get_task(tid)

    t = asyncio.run(go())
    assert t["status"] == "done" and t["metadata"]["run_seconds"] == 0
    assert TasksFeature._card(t)["metadata"]["run_seconds"] == 0
    feature.store.close()


# ---------------------------------------------------------------- "Javis is asking you" vs "Javis is handling it"
# Owner, 30/10/2026: "Needs you" made low-tech owners anxious about stopped jobs they could not fix, and need not.

def _stopped_board(tmp_path):
    feature, brain = _feature(tmp_path)
    root = feature._ensure(brain)
    s = feature.store
    ids = {}
    for name in ("question", "permission", "review", "technical", "limit"):
        ids[name] = s.enqueue(root, name, "x", capability="files", status="ready", max_attempts=1)
        assert s.claim(ids[name], "w")
    s.ask(ids["question"], "w", "Which file?")
    s.block(ids["permission"], "w", "capability", "needs to send for real")
    s.complete(ids["review"], "w", "draft", needs_approval=True)
    s.block(ids["technical"], "w", "transient", "ConnectionResetError: [Errno 104] peer reset")
    s.block(ids["limit"], "w", "limit", "Gói Claude hết lượt, mốc mở lại quá xa để tự đợi (Nov 3).")
    return feature, brain, root, ids


def test_only_what_the_owner_alone_can_move_on_asks_for_them(tmp_path):
    feature, brain, root, ids = _stopped_board(tmp_path)
    ops = feature.board_view(brain)["operations"]
    asking = {t["title"] for t in ops["attention"]}
    handled = {t["title"]: t for t in ops["handled"]}
    assert asking == {"question", "permission", "review"}, asking
    assert set(handled) == {"technical", "limit"}, set(handled)
    tech = handled["technical"]["calm"]
    assert "không cần làm gì" in tech and "ConnectionResetError" not in tech
    assert handled["limit"]["calm"].startswith("Gói Claude hết lượt")
    assert all(t["waits_for_owner"] for t in ops["attention"])
    # The raw error is still there for the drawer's technical detail.
    assert "ConnectionResetError" in handled["technical"]["block_reason"]
    feature.store.close()


def test_wiping_one_area_leaves_the_other(tmp_path):
    feature, brain, root, ids = _stopped_board(tmp_path)
    assert feature.store.archive_attention(root, owner=False) == 2
    ops = feature.board_view(brain)["operations"]
    assert ops["handled"] == [] and len(ops["attention"]) == 3
    assert feature.store.archive_attention(root, owner=True) == 3
    assert feature.board_view(brain)["operations"]["attention"] == []
    feature.store.close()


def test_a_technical_pause_is_reported_quietly_and_asks_nothing(tmp_path):
    import tasks as tasks_mod
    feature, brain = _feature(tmp_path)
    sent = []

    async def report(chat_id, text, quiet=False, **kw):
        sent.append({"text": text, "quiet": quiet})
        return True

    feature.deps.report = report
    tasks_mod.BAO_GOM_GIAY = 0.05

    async def go():
        base = {"status": "blocked", "chat_id": "web:a", "brain_root": brain}
        await feature._report({**base, "id": "a", "title": "Sync sheet", "block_kind": "transient",
                               "block_reason": "HTTP 502 from sheets.googleapis.com"})
        await feature._report({**base, "id": "b", "title": "Post the article", "block_kind": "capability",
                               "block_reason": "needs to post for real"})
        await asyncio.sleep(0.3)

    asyncio.run(go())
    tech = [m for m in sent if "Sync sheet" in m["text"]]
    perm = [m for m in sent if "Post the article" in m["text"]]
    assert len(tech) == 1 and len(perm) == 1, sent
    assert tech[0]["quiet"] is True and "không cần làm gì" in tech[0]["text"]
    assert "⚠" not in tech[0]["text"] and "cần bạn xem" not in tech[0]["text"]
    assert tech[0]["text"].index("không cần làm gì") < tech[0]["text"].index("HTTP 502")
    assert perm[0]["quiet"] is False and "cho phép" in perm[0]["text"]
    feature.store.close()


def test_store_keeps_old_boards_working(tmp_path):
    """A store from before 0.411.0 gains the hint table on open; nothing else changes shape."""
    path = tmp_path / "q.sqlite3"
    s = TaskStore(path)
    s.close()
    s = TaskStore(path)
    root = str(tmp_path / "b")
    s.dismiss_hint(root, "a b")
    s.dismiss_hint(root, "a b")
    assert s.repeat_hints(root) == []
    s.close()


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
