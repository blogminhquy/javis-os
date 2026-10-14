"""0.107.0: field report 2026-10-13 (javis.fiona-tools.com), twelve items. This file pins the
code fixes so they do not slide back:

- Kanban checks acceptance before Done (t_784c7a7b8fd6 went Done with "chưa xong").
- The block reason is the [[NEEDS_INPUT]] line or the verdict, not the trailing disclaimer
  (t_ae9309c4c70e showed "Đây là duyệt tự động của worker...").
- A blocked parent names the jobs waiting on it (t_555f8db43bd7 sat in Todo silently).
- Capability "image" grants exactly the image tools; a workflow step can declare `tools:`.
- javis_task takes `route` (wf:<slug> of a real workflow) and warns on route auto.
- Workflow verify is fail-closed and a step still failing after its retries stops the run.
- A switched-off workflow does not run from Kanban; `status: off` (YAML False) reads as off.
- Script reminders do not wait on the task-mode lock.
- Rotated chat threads count as chat on the usage page.

    python tests/python/test_kanban_nghiem_thu_va_quy_trinh.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

import plugins_host
import workflow_graph as wg
from task_store import TaskStore
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
    return TasksFeature(deps), brain


# ---------------------------------------------------------------- block reason

def test_reason_is_the_needs_input_line_not_the_trailing_disclaimer():
    raw = ("[[NEEDS_INPUT]] KHÔNG ĐẠT: chữ trên ảnh sai, ghi 'Fiona S70' thay vì 'Fiona S07'.\n"
           "## Chi tiết\n- Ảnh gốc thấy: có\n- Ảnh thành phẩm thấy: có\n\n"
           "Đây là duyệt tự động của worker, không phải chủ duyệt.")
    reason = TasksFeature._needs_input_reason(raw)
    assert "Fiona S70" in reason and "duyệt tự động" not in reason


def test_reason_prefers_the_verdict_line_when_the_marker_stands_alone():
    raw = ("[[NEEDS_INPUT]]\n# Duyệt ảnh nháp Fiona S07\n"
           "**Kết luận: KHÔNG ĐẠT** - sai chữ trên ảnh.\n"
           "Đây là duyệt tự động của worker, không phải chủ duyệt.")
    reason = TasksFeature._needs_input_reason(raw)
    assert reason.startswith("Kết luận: KHÔNG ĐẠT") and "**" not in reason


def test_reason_still_falls_back_to_the_last_line():
    raw = "[[NEEDS_INPUT]]\nTôi đã đọc file A.\nTôi đã đọc file B.\nBonus cộng theo gói nào?"
    assert "Bonus cộng theo gói nào" in TasksFeature._needs_input_reason(raw)


def test_marker_counts_only_at_the_start_of_a_line():
    # Field report 14/10/2026 on 0.108.0 (t_dbe86f05c62f): a finished job was blocked because the
    # worker mentioned the marker inside a sentence saying it was not needed.
    from tasks import asks_for_input
    assert asks_for_input("[[NEEDS_INPUT]] Thiếu ảnh vuông.")
    assert asks_for_input("Báo cáo\n- **[[NEEDS_INPUT]]** thiếu ảnh")
    assert asks_for_input("> [[NEEDS_INPUT]] cần chủ chọn mẫu")
    assert asks_for_input("Bước 3 xong\n[[NEEDS_INPUT]] Workflow dừng chờ duyệt bước 4")
    assert not asks_for_input("Đủ đầu ra theo điều kiện hoàn thành, không cần ghi [[NEEDS_INPUT]].")
    assert not asks_for_input("Theo mục 9, chỉ mở đầu bằng [[NEEDS_INPUT]] khi thiếu đầu ra; ở đây đã đủ.")
    assert not asks_for_input("")


def test_reason_ignores_a_marker_mentioned_mid_sentence():
    raw = ("[[NEEDS_INPUT]] Thiếu ảnh thành phẩm của F10Z.\n"
           "Ghi chú: theo luật thì [[NEEDS_INPUT]] chỉ dùng khi thiếu đầu ra.")
    assert TasksFeature._needs_input_reason(raw).startswith("Thiếu ảnh thành phẩm")


def test_finished_worker_that_mentions_the_marker_is_done(tmp_path):
    feature, brain = _feature(tmp_path)
    feature._base_cli = lambda *a, **k: object()

    async def query(cli, prompt):
        if "autonomous worker" in prompt:
            return ("Đã xem kết quả kiểm chứng 2 ảnh F10Z 8.0 lắp máy và quyết định giữ ảnh 1.\n"
                    "Đạt đủ điều kiện hoàn thành nên không cần ghi [[NEEDS_INPUT]]."), "", []
        return '{"pass": true, "missing": ""}', "", []

    feature._query = query
    t = _run(feature, {"brain_root": str(brain), "title": "F10Z", "intent": "Xem kết quả kiểm chứng và quyết định",
                       "acceptance": ["Có quyết định giữ ảnh nào"]}, feature._execute)
    assert t["status"] == "done", (t["status"], t.get("block_reason"))


# ---------------------------------------------------------------- acceptance

def test_unfinished_admission_is_read_only_from_the_top():
    assert TasksFeature._admits_unfinished("Chạy thử chưa xong: 3 bước ảnh không chạy được.\n...")
    assert not TasksFeature._admits_unfinished(
        "Đã tạo bài và ảnh vuông.\nĐã kiểm chứng.\nGhi chú: lần thử đầu bước ảnh chưa xong, "
        "lần hai thì được.")


def _run(feature, task, execute):
    feature._execute = execute

    async def go():
        root = feature._ensure(task["brain_root"])
        tid = feature.store.enqueue(root, task["title"], task["intent"], capability="files",
                                    status="ready")
        if task.get("acceptance"):
            # Same place the specifier writes it.
            with feature.store._lock:
                feature.store._db.execute(
                    "UPDATE tasks SET metadata_json=? WHERE id=?",
                    (json.dumps({"acceptance": task["acceptance"]}), tid))
                feature.store._db.commit()
        assert await feature._claim_and_spawn(tid)
        await feature._workers[tid]
        return feature.store.get_task(tid)
    return asyncio.run(go())


def test_worker_that_says_it_did_not_finish_is_not_done(tmp_path):
    feature, brain = _feature(tmp_path)

    async def execute(task):
        return ("Chạy thử chưa xong. 3 bước ảnh (4-6) không chạy được vì thiếu công cụ ảnh.",
                "", False, {})

    t = _run(feature, {"brain_root": str(brain), "title": "S07", "intent": "x"}, execute)
    assert t["status"] == "blocked", t["status"]
    assert "chưa xong" in (t.get("block_reason") or "")


def test_acceptance_checker_verdict_decides(tmp_path):
    feature, brain = _feature(tmp_path)
    feature._base_cli = lambda *a, **k: object()
    seen = []

    async def query(cli, prompt):
        seen.append(prompt)
        return '{"pass": false, "missing": "Không có ảnh vuông nào trong attachments/."}', "", []

    feature._query = query

    async def execute(task):
        return "Đã làm xong bài đăng và ảnh.", "", False, {}

    t = _run(feature, {"brain_root": str(brain), "title": "S07b", "intent": "x",
                       "acceptance": ["Có ảnh vuông 1:1 trong attachments/"]}, execute)
    assert t["status"] == "blocked"
    assert "ảnh vuông" in t["block_reason"]
    assert seen and "Có ảnh vuông 1:1" in seen[0] and "Đã làm xong bài đăng" in seen[0]


def test_acceptance_pass_marks_done_and_records_how(tmp_path):
    feature, brain = _feature(tmp_path)
    feature._base_cli = lambda *a, **k: object()

    async def query(cli, prompt):
        return '{"pass": true, "missing": ""}', "", []

    feature._query = query

    async def execute(task):
        return "Đã làm xong.", "", False, {"provider": "t"}

    t = _run(feature, {"brain_root": str(brain), "title": "S07c", "intent": "x",
                       "acceptance": ["file a.md có"]}, execute)
    assert t["status"] == "done"
    assert t["metadata"].get("acceptance_check") == "ai"


def test_a_checker_that_cannot_run_does_not_rerun_or_block_the_job(tmp_path):
    feature, brain = _feature(tmp_path)
    feature._base_cli = lambda *a, **k: object()

    async def query(cli, prompt):
        return "", "Engine chưa sẵn sàng", []

    feature._query = query

    async def execute(task):
        return "Đã làm xong.", "", False, {}

    t = _run(feature, {"brain_root": str(brain), "title": "S07d", "intent": "x",
                       "acceptance": ["file a.md có"]}, execute)
    assert t["status"] == "done"
    assert t["metadata"].get("acceptance_check") == "unverified"


# ---------------------------------------------------------------- dependents

def test_blocked_parent_names_the_jobs_waiting_on_it(tmp_path):
    reports = []
    feature, brain = _feature(tmp_path, reports)
    root = feature._ensure(str(brain))
    parent = feature.store.enqueue(root, "Duyệt ảnh", "x", capability="files", status="ready")
    feature.store.enqueue(root, "Bóc lỗi", "y", deps=[parent], capability="files", status="todo")
    assert [t["title"] for t in feature.store.waiting_on(parent)] == ["Bóc lỗi"]

    async def go():
        await feature._gom_bao({"id": parent, "title": "Duyệt ảnh", "chat_id": "web:s",
                                "block_reason": "KHÔNG ĐẠT"})
        await feature._xa_bao("web:s")
    asyncio.run(go())
    text = reports[-1][0][1]
    assert "Bóc lỗi" in text and "KHÔNG ĐẠT" in text


# ---------------------------------------------------------------- image capability

def test_image_capability_grants_only_the_image_tools(tmp_path):
    feature, _brain = _feature(tmp_path)
    tools, mode, disallowed = feature._lane_tools({"capability": "image", "execution_mode": "auto"})
    assert "mcp__javis-plugins__javis_generate_image" in tools
    assert "mcp__javis-plugins__javis_describe_image" in tools
    assert not any("fb_" in t or "zalo" in t for t in tools)
    assert "Bash" in disallowed and mode == "auto"
    assert plugins_host.granted_plugin_tools(tools) == {"javis_generate_image", "javis_describe_image"}


def test_heuristic_spec_picks_image_without_eating_anh_huong(tmp_path):
    feature, _ = _feature(tmp_path)
    assert feature._heuristic_spec({"title": "Tạo ảnh vuông cho bài S07"})["capability"] == "image"
    assert feature._heuristic_spec({"title": "Ghi chú ảnh hưởng của giá"})["capability"] == "files"


def test_grant_patterns_reject_odd_names():
    assert plugins_host.grant_patterns(["javis_generate_image", "Bash", "x;rm", ""]) == [
        "mcp__javis-plugins__javis_generate_image", "mcp__javis__javis_generate_image"]


# ---------------------------------------------------------------- workflow helpers

def test_workflow_status_reads_yaml_booleans():
    assert wg.workflow_status({"status": False}) == "off"     # `status: off` unquoted
    assert wg.workflow_status({"status": True}) == "active"   # `status: on`
    assert wg.workflow_status({"status": "active"}) == "active"
    assert wg.workflow_status({"status": "off"}) == "off"
    assert wg.workflow_status({}) == "off"


def test_step_tools_parse():
    assert wg.step_tools({"tools": ["javis_generate_image", "javis_generate_image", "x y"]}) == (
        "javis_generate_image",)
    assert wg.step_tools({"tools": "WebFetch, javis_describe_image"}) == (
        "WebFetch", "javis_describe_image")
    assert wg.step_tools({}) == ()
    g = wg.compile_legacy_workflow({"steps": [
        {"agent": "a", "task": "t", "tools": ["javis_generate_image"]},
        {"agent": "b", "task": "t"}]}, "demo")
    assert g.nodes[0].metadata.get("tools") == ["javis_generate_image"]
    assert "tools" not in g.nodes[1].metadata


# ---------------------------------------------------------------- javis_task route

def _task_plugin():
    spec = importlib.util.spec_from_file_location(
        "javis_task_plugin_t", ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_javis_task_route(tmp_path, monkeypatch):
    import tasks as tasks_mod
    m = _task_plugin()
    feature, brain = _feature(tmp_path)
    wf = brain / "workflows"
    wf.mkdir()
    (wf / "quy-trinh-chuan-bai-dang-va-anh.md").write_text(
        "---\nname: Quy trình chuẩn bài đăng và ảnh\nstatus: active\nsteps: []\n---\n",
        encoding="utf-8")
    (wf / "ban-nhap.md").write_text("---\nname: Bản nháp\nstatus: off\nsteps: []\n---\n",
                                    encoding="utf-8")
    monkeypatch.setattr(tasks_mod, "current", lambda: feature)

    class Ctx:
        vault_root = str(brain)

    out = m._them({"title": "Chạy S07", "route": "wf:khong-co", "chat_id": "web:s"}, Ctx())
    assert out.startswith("ERROR") and "quy-trinh-chuan-bai-dang-va-anh" in out

    out = m._them({"title": "Chạy S07", "route": "wf:quy-trinh-chuan-bai-dang-va-anh",
                   "chat_id": "web:s"}, Ctx())
    assert "Chạy quy trình: wf:quy-trinh-chuan-bai-dang-va-anh" in out
    tid = out.split("Mã việc: ")[1].split("\n")[0]
    assert feature.store.get_task(tid)["route"] == "wf:quy-trinh-chuan-bai-dang-va-anh"

    out = m._them({"title": "Chạy nháp", "route": "wf:ban-nhap", "chat_id": "web:s"}, Ctx())
    assert "đang TẮT" in out

    out = m._them({"title": "S07 theo Quy trình chuẩn bài đăng và ảnh", "chat_id": "web:s"}, Ctx())
    assert "CẢNH BÁO" in out and "wf:quy-trinh-chuan-bai-dang-va-anh" in out


def test_kanban_turns_a_needs_input_workflow_error_into_needs_input(tmp_path):
    async def stopped(brain_root, slug, intent, tools, source="other", mode=None):
        assert mode == "auto"
        yield {"type": "error", "needs_input": True, "content": "Bước 2 chưa qua kiểm chứng"}

    feature, brain = _feature(tmp_path)
    feature.deps.execute_workflow = stopped
    result, error, needs_input, _ = asyncio.run(feature._execute({
        "route": "wf:demo", "intent": "x", "brain_root": str(brain),
        "capability": "files", "execution_mode": "auto"}))
    assert needs_input and not error and "Bước 2 chưa qua kiểm chứng" in result


# ---------------------------------------------------------------- workflow runner (main)

def _brain(tmp_path, monkeypatch, verify_answers, status="active", step_extra=""):
    import config as cfgmod
    import copy
    import main

    brain = tmp_path / "brain"
    (brain / "workflows").mkdir(parents=True)
    (brain / "agents").mkdir(parents=True)
    (brain / "workflows" / "demo.md").write_text(
        "---\ntype: workflow\nname: Demo\nslug: demo\nstatus: " + status + "\nsteps:\n"
        "  - agent: writer\n    task: 'Viết {{input}}'\n    verify_agent: checker\n"
        "    max_retries: 1\n" + step_extra +
        "  - agent: poster\n    task: 'Đăng {{prev}}'\n---\n", encoding="utf-8")
    for slug in ("writer", "checker", "poster"):
        (brain / "agents" / f"{slug}.md").write_text(
            f"---\ntype: agent\nname: {slug}\nslug: {slug}\nrole: r\nskills: []\n---\nthân\n",
            encoding="utf-8")
    calls, engines = [], []
    answers = list(verify_answers)

    class FakeEngine:
        def __init__(self, **k):
            self.model = None
            self.kw = k
            engines.append(self)

        async def query(self, prompt):
            calls.append(prompt)
            if "KẾT QUẢ CẦN KIỂM CHỨNG" in prompt:
                a = answers.pop(0) if answers else ""
                if a == "__ERROR__":
                    yield {"type": "error", "content": "engine chết"}
                    return
                yield {"type": "final", "content": a}
                return
            yield {"type": "final", "content": f"KQ({len(calls)})"}

    monkeypatch.setattr(main, "claude_engine", lambda **k: FakeEngine(**k))
    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_workflows_dir", lambda b: brain / "workflows")
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    monkeypatch.setattr(main, "_log_agent_run", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda *a, **k: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda *a, **k: None)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: copy.deepcopy(cfgmod._DEFAULT))
    return main, calls, engines


def _drain(gen):
    async def go():
        return [x async for x in gen]
    return asyncio.run(go())


def test_verdict_parsing_is_fail_closed():
    import main
    assert main._workflow_verdict('{"pass": true, "reason": "ok"}')[0] is True
    assert main._workflow_verdict('{"pass": "false"}')[0] is False
    assert main._workflow_verdict("", "engine chết")[0] is False
    assert main._workflow_verdict("Tôi thấy bài ổn.")[0] is False
    assert main._workflow_verdict("CỔNG NỘI DUNG: CHƯA ĐẠT - thiếu giá")[0] is False
    assert main._workflow_verdict("CỔNG NỘI DUNG: ĐẠT")[0] is True


def test_step_still_failing_after_retries_stops_the_run(tmp_path, monkeypatch):
    fail = '{"pass": false, "reason": "thiếu giá", "fixes": "thêm giá"}'
    main, calls, _ = _brain(tmp_path, monkeypatch, [fail, fail])
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07"))
    kinds = [e["type"] for e in events]
    assert "done" not in kinds
    err = [e for e in events if e["type"] == "error"][-1]
    assert err.get("needs_input") and "thiếu giá" in err["content"]
    assert not any(p.startswith("Đăng") for p in calls), "bước sau không được chạy"


def test_verify_engine_error_is_not_a_pass(tmp_path, monkeypatch):
    main, calls, _ = _brain(tmp_path, monkeypatch, ["__ERROR__", "__ERROR__"])
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07"))
    assert "done" not in [e["type"] for e in events]
    results = [e for e in events if e["type"] == "step_verify_result"]
    assert results and all(r["passed"] is False for r in results)


def test_verify_pass_runs_on(tmp_path, monkeypatch):
    main, calls, _ = _brain(tmp_path, monkeypatch, ['{"pass": true, "reason": "ok"}'])
    events = _drain(main._execute_workflow_raw("brain", "demo", input="S07"))
    assert events[-1]["type"] == "done"


def test_switched_off_workflow_does_not_run_from_kanban(tmp_path, monkeypatch):
    main, calls, _ = _brain(tmp_path, monkeypatch, [], status="off")   # YAML -> False
    events = _drain(main.execute_workflow("brain", "demo", input="x", source="kanban"))
    assert len(events) == 1 and events[0]["type"] == "error" and events[0].get("needs_input")
    assert not calls


def test_step_tools_reach_a_gated_run(tmp_path, monkeypatch):
    ok = '{"pass": true}'
    main, calls, engines = _brain(tmp_path, monkeypatch, [ok], step_extra=(
        "    tools: [javis_generate_image, WebSearch, Bash]\n"))
    _drain(main._execute_workflow_raw("brain", "demo", input="x",
                                      tools=["Read", "Write"], mode="auto"))
    writer = engines[0]
    allowed = writer.kw["allowed_tools"]
    assert "mcp__javis-plugins__javis_generate_image" in allowed and "WebSearch" in allowed
    assert "Bash" not in allowed and "Bash" in writer.disallowed_tools
    assert "WebSearch" not in writer.disallowed_tools
    assert getattr(writer, "javis_mode", None) == "auto"
    # The verify agent and the next step get nothing extra.
    for e in engines[1:]:
        assert not any("javis-plugins" in t for t in e.kw["allowed_tools"])


# ---------------------------------------------------------------- reminders

def test_script_reminder_does_not_wait_on_the_task_lock():
    import reminders
    feat = reminders.RemindersFeature.__new__(reminders.RemindersFeature)
    feat.lock = asyncio.Lock()
    feat.script_lock = asyncio.Lock()
    assert feat._khoa("script") is feat.script_lock
    assert feat._khoa("task") is feat.lock


# ---------------------------------------------------------------- usage page

def test_resume_marker_matches_compaction():
    import compaction
    import usage_index
    prompt = compaction.bootstrap_prompt([{"role": "user", "content": "chào"}], "hỏi tiếp")
    assert prompt.startswith(usage_index.CHAT_RESUME_MARKER)


def test_rotated_chat_threads_count_as_chat(tmp_path, monkeypatch):
    import usage_index
    db = tmp_path / "conversations.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE sessions(id TEXT, cli_session_id TEXT)")
    c.execute("CREATE TABLE cli_session_history(cli_session_id TEXT PRIMARY KEY, session_id TEXT, bound_at REAL)")
    c.execute("INSERT INTO sessions VALUES('conv', 'thread-3')")
    c.execute("INSERT INTO cli_session_history VALUES('thread-1', 'conv', 1)")
    c.commit()
    c.close()
    monkeypatch.setattr(usage_index, "_conversations_db", lambda: db)
    assert usage_index._chat_sessions() == {"thread-3", "thread-1"}

    user_line = {"type": "user", "sessionId": "thread-2",
                 "message": {"content": usage_index.CHAT_RESUME_MARKER + "\nlịch sử..."}}
    assert usage_index._mo_dau_khoi_phuc(user_line)
    assert not usage_index._mo_dau_khoi_phuc({"type": "user", "message": {"content": "chào"}})


def test_sessions_store_keeps_every_thread(tmp_path):
    import sessions
    st = sessions.SessionStore(tmp_path / "c.db")
    sid = st.create_session(title="t", brain="brain")
    st.set_cli_session_id(sid, "a")
    st.set_cli_session_id(sid, "b")
    st.set_cli_session_id(sid, "a")
    rows = sqlite3.connect(tmp_path / "c.db").execute(
        "SELECT cli_session_id FROM cli_session_history ORDER BY bound_at").fetchall()
    assert [r[0] for r in rows] == ["a", "b"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
