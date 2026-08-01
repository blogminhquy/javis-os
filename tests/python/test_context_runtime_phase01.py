from _paths import ROOT, SERVER  # noqa: E402,F401

import json
import sqlite3
from pathlib import Path

from context_runtime import (
    ObserveRuntime,
    bind_trace,
    current_trace,
    payload_attribution,
    reset_trace,
)


def _settings(mode="observe", retention=14):
    return {"context_runtime": {
        "mode": mode,
        "retention_days": retention,
        "store_content": True,  # runtime Phase 0-1 phải ép false dù bị sửa tay
        "estimate_chars_per_token": 3.0,
    }}


def test_payload_attribution_only_returns_sizes():
    secret_text = "noi dung rieng khong duoc luu"
    meta = payload_attribution(
        [{"role": "system", "content": "luat"},
         {"role": "user", "content": secret_text}],
        [{"name": "demo", "schema": {"type": "object"}}],
        chars_per_token=3.0,
    )
    assert meta["system_chars"] == 4
    assert meta["user_chars"] == len(secret_text)
    assert meta["message_count"] == 2
    assert meta["tool_count"] == 1
    assert secret_text not in json.dumps(meta, ensure_ascii=False)


def test_payload_attribution_splits_scaling_sources_without_storing_them():
    system = (
        "CORE PRIVATE\n"
        "# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===\nMEMORY PRIVATE\n"
        "# === SKILL KHẢ DỤNG (router) ===\nSKILL PRIVATE\n"
        "# === KÊNH HỘI THOẠI HIỆN TẠI ===\nCHANNEL PRIVATE"
    )
    meta = payload_attribution([
        {"role": "system", "content": system},
        {"role": "system", "content": "ROLLING SUMMARY PRIVATE"},
        {"role": "user", "content": "OLD USER PRIVATE"},
        {"role": "assistant", "content": "OLD ASSISTANT PRIVATE"},
        {"role": "user", "content": "CURRENT USER PRIVATE"},
    ])
    assert meta["core_contract_chars"] > 0
    assert meta["memory_index_chars"] > 0
    assert meta["skill_router_chars"] > 0
    assert meta["channel_contract_chars"] > 0
    assert meta["unclassified_system_chars"] == len("ROLLING SUMMARY PRIVATE")
    assert meta["history_user_chars"] == len("OLD USER PRIVATE")
    assert meta["current_user_chars"] == len("CURRENT USER PRIVATE")
    encoded = json.dumps(meta, ensure_ascii=False)
    for private in ("CORE PRIVATE", "MEMORY PRIVATE", "SKILL PRIVATE", "CURRENT USER PRIVATE"):
        assert private not in encoded


def test_runtime_lifecycle_reconciles_usage_and_never_persists_content(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    trace = runtime.start_turn("sid-1", r"D:\brain\demo", "dashboard")
    assert trace is not None

    raw_user = "SECRET USER MESSAGE 123456"
    raw_system = "SECRET SYSTEM PROMPT 654321"
    raw_tool = "SECRET TOOL DESCRIPTION 777777"
    runtime.set_route(trace, "groq", "llama-test")
    runtime.observe_payload(
        trace,
        [{"role": "system", "content": raw_system},
         {"role": "user", "content": raw_user}],
        [{"name": "demo", "description": raw_tool}],
        provider="groq", model="llama-test",
    )
    runtime.record_usage(trace, 321, 45)
    runtime.finish(trace)

    task = runtime.get_task(trace.task_id)
    assert task["status"] == "COMPLETED"
    assert task["runtime_version"] == "adaptive-v5"
    assert task["resolver_policy_version"]
    assert task["compiler_policy_version"]
    assert task["registry_revision"]
    assert task["model_profile_revision"]

    events = runtime.list_events(trace.task_id)
    assert [e["event_type"] for e in events] == [
        "task.started", "route.observed", "payload.observed",
        "usage.observed", "task.finished",
    ]
    payload = next(e["payload"] for e in events if e["event_type"] == "payload.observed")
    assert payload["message_count"] == 2
    assert payload["tool_count"] == 1
    assert "content" not in payload

    runtime.close()
    db_bytes = (tmp_path / "runtime.db").read_bytes()
    for raw in (raw_user, raw_system, raw_tool):
        assert raw.encode("utf-8") not in db_bytes

    db = sqlite3.connect(tmp_path / "runtime.db")
    step = db.execute(
        "SELECT estimated_input_tokens,actual_input_tokens,actual_output_tokens "
        "FROM runtime_steps WHERE id=?", (trace.step_id,)
    ).fetchone()
    assert step[0] > 0
    assert step[1:] == (321, 45)
    statuses = [r[0] for r in db.execute(
        "SELECT status FROM quota_reservations WHERE task_id=?", (trace.task_id,)
    ).fetchall()]
    assert statuses == ["RECONCILED"]


def test_multiround_usage_is_accumulated_and_reservations_reconcile_one_by_one(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    trace = runtime.start_turn("sid", "brain", "dashboard")
    messages = [{"role": "user", "content": "synthetic"}]
    first = runtime.observe_payload(trace, messages, provider="groq", model="m")
    second = runtime.observe_payload(trace, messages, provider="groq", model="m")
    runtime.record_usage(trace, 100, 10)

    db = sqlite3.connect(tmp_path / "runtime.db")
    assert db.execute(
        "SELECT status,COUNT(*) FROM quota_reservations GROUP BY status"
    ).fetchall() == [("OBSERVED", 1), ("RECONCILED", 1)]
    runtime.record_usage(trace, 200, 20)
    assert db.execute(
        "SELECT actual_input_tokens,actual_output_tokens FROM runtime_steps WHERE id=?",
        (trace.step_id,),
    ).fetchone() == (300, 30)
    assert db.execute(
        "SELECT estimated_input_tokens FROM runtime_steps WHERE id=?", (trace.step_id,)
    ).fetchone()[0] == first["estimated_input_tokens"] + second["estimated_input_tokens"]
    assert db.execute(
        "SELECT COUNT(*) FROM quota_reservations WHERE status='RECONCILED'"
    ).fetchone()[0] == 2
    runtime.finish(trace)


def test_budget_deadline_evidence_ref_and_optimistic_version_guard(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    trace = runtime.start_turn(
        "sid", "brain", "dashboard",
        token_budget={"input_tokens": 12000, "enforced": False},
        deadline_seconds=60,
    )
    evidence = runtime.add_evidence_ref(trace, "tool_result", "PRIVATE SOURCE REF")
    assert evidence and evidence.startswith("re_")

    db = sqlite3.connect(tmp_path / "runtime.db")
    task = db.execute(
        "SELECT budget_json,deadline_at,version FROM runtime_tasks WHERE id=?",
        (trace.task_id,),
    ).fetchone()
    assert json.loads(task[0])["input_tokens"] == 12000
    assert task[1] is not None
    assert task[2] == 1
    assert b"PRIVATE SOURCE REF" not in (tmp_path / "runtime.db").read_bytes()

    # Giả lập worker khác đã cập nhật task: worker cũ không được đè state mới.
    db.execute("UPDATE runtime_tasks SET version=2 WHERE id=?", (trace.task_id,))
    db.commit()
    assert runtime.finish(trace) is False
    assert db.execute(
        "SELECT status,version FROM runtime_tasks WHERE id=?", (trace.task_id,)
    ).fetchone() == ("RUNNING", 2)
    assert db.execute(
        "SELECT event_type FROM runtime_events WHERE task_id=? ORDER BY seq DESC LIMIT 1",
        (trace.task_id,),
    ).fetchone()[0] == "task.version_conflict"


def test_mode_off_creates_no_database(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings("off"))
    assert runtime.start_turn("sid", "brain", "dashboard") is None
    assert not (tmp_path / "runtime.db").exists()


def test_trace_context_is_task_local(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    trace = runtime.start_turn("sid", "brain", "dashboard")
    token = bind_trace(trace)
    try:
        assert current_trace() is trace
    finally:
        reset_trace(token)
    assert current_trace() is None
    runtime.close()


def test_gold_fixture_is_synthetic_and_structurally_complete():
    fixture = json.loads((ROOT / "tests/fixtures/context_runtime_gold.json").read_text(encoding="utf-8"))
    assert fixture["privacy"] == "synthetic-only"
    assert len(fixture["cases"]) >= 5
    ids = set()
    for case in fixture["cases"]:
        assert case["id"] not in ids
        ids.add(case["id"])
        assert case["objective"]
        assert isinstance(case["allowed_capabilities"], list)
        assert isinstance(case["forbidden_effects"], list)
        assert case["required_contracts"]


def test_legacy_prompt_contract_baseline():
    source = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    fixture = json.loads(
        (ROOT / "tests/fixtures/context_runtime_prompt_contract.json").read_text(encoding="utf-8")
    )
    for contract in fixture["contracts"]:
        assert any(term in source for term in contract["any_of"]), contract["id"]


def test_context_runtime_default_is_shadow_and_metadata_only():
    config_source = (SERVER / "config.py").read_text(encoding="utf-8")
    runtime_source = (SERVER / "context_runtime.py").read_text(encoding="utf-8")
    assert '"mode": "shadow"' in config_source
    assert '"store_content": False' in runtime_source
    for sensitive in ("content", "prompt", "messages", "objective", "query", "secret"):
        assert f'"{sensitive}"' in runtime_source
