from _paths import ROOT, SERVER  # noqa: E402,F401

import asyncio
import inspect
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from capability_registry import CapabilityRegistry
from capability_resolver import DeterministicResolver
from context_compiler import ContextCompiler
from context_runtime import ObserveRuntime
from fast_path_runtime import (
    CanaryPolicy,
    FastIntentClassifier,
    FastPathCanary,
    FastPathPlan,
    stable_bucket,
)


def _settings(allocation=10_000, rolling_tpm=12_000, mode="canary"):
    return {
        "context_runtime": {
            "mode": mode,
            "retention_days": 14,
            "canary": {
                "policy_version": "test-fast-v1",
                "allocation_basis_points": allocation,
                "salt": "test-salt-v1",
                "channels": ["dashboard"],
                "provider_kinds": ["api"],
                "registry_max_age_seconds": 900,
                "estimator_safety_factor": 1.35,
                "quota_profiles": [{
                    "id": "groq-test",
                    "provider": "groq",
                    "model_pattern": "llama-*",
                    "rolling_tpm": rolling_tpm,
                    "max_input_tokens": 8000,
                    "reserved_output_tokens": 600,
                    "window_seconds": 60,
                }],
            },
        }
    }


def _stack(tmp_path, settings=None):
    settings = settings or _settings()
    brain = tmp_path / "brain"
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_tools(brain, [], {})
    resolver = DeterministicResolver(registry)
    compiler = ContextCompiler(registry)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-alpha", str(brain), "dashboard")
    # ObserveRuntime singleton production lấy revision của registry production. Test stack dùng
    # registry cô lập nên pin revision tương ứng vào trace trước admission.
    trace.registry_revision = registry.revision(brain)
    canary = FastPathCanary(
        registry, resolver, compiler, runtime, settings_reader=lambda: settings,
    )
    return brain, registry, runtime, trace, canary


def test_stable_bucket_is_deterministic_and_session_scoped():
    assert stable_bucket("sid-a", "v1") == stable_bucket("sid-a", "v1")
    assert stable_bucket("sid-a", "v1") != stable_bucket("sid-b", "v1")
    assert 0 <= stable_bucket("sid-a", "v1") < 10_000


def test_policy_is_disabled_without_explicit_allocation_and_hard_quota():
    policy = CanaryPolicy.from_settings({"context_runtime": {"mode": "canary"}})
    assert policy.allocation_basis_points == 0
    assert policy.quota_rule("groq", "llama-3") is None


def test_classifier_is_conservative_for_live_tool_write_memory_and_attachments():
    gate = FastIntentClassifier()
    assert gate.classify("Giải thích entropy là gì").eligible
    assert gate.classify("Viết cho anh 5 tiêu đề về học tập").eligible
    for prompt in (
        "Thời tiết hôm nay thế nào?",
        "Đọc file trong vault giúp anh",
        "Xóa lịch họp ngày mai",
        "Anh đã nói gì với em lần trước?",
        "Kiểm tra giúp anh trên internet",
    ):
        assert not gate.classify(prompt).eligible, prompt
    assert not gate.classify("Tóm tắt nội dung", has_attachments=True).eligible


def test_canary_compiles_small_identity_capsule_and_pins_task(tmp_path):
    brain, registry, runtime, trace, canary = _stack(tmp_path)
    objective = "Giải thích entropy là gì"
    plan = canary.prepare(
        trace, objective, str(brain), "dashboard", "groq", "llama-3.3", "api"
    )
    assert plan.action == "execute"
    assert plan.execution_path == "fast"
    assert plan.reservation_id.startswith("qa_")
    assert len(plan.messages) == 2
    system = plan.messages[0]["content"]
    assert "provider=groq" in system and "model=llama-3.3" in system
    assert objective == plan.messages[1]["content"]
    assert len(json.dumps(plan.messages, ensure_ascii=False)) < 5000
    task = runtime.get_task(trace.task_id)
    assert task["execution_path"] == "fast"
    assert task["canary_policy_version"] == "test-fast-v1"
    assert any(e["event_type"] == "quota.admitted" for e in runtime.list_events(trace.task_id))

    runtime.close()
    raw = (tmp_path / "runtime" / "runtime.db").read_bytes()
    assert objective.encode("utf-8") not in raw
    registry.close()


def test_fast_workload_reduces_total_input_not_just_one_prompt(tmp_path):
    settings = _settings(rolling_tpm=1_000_000)
    brain, registry, runtime, first_trace, canary = _stack(tmp_path, settings)
    prompts = (
        "Giải thích entropy là gì",
        "Viết cho anh 5 tiêu đề về học tập",
        "Tóm tắt đoạn sau: hệ thống tốt cần quan sát được và có đường rollback.",
        "Phân biệt throughput và latency",
        "Brainstorm 10 ý tưởng tên cho ứng dụng ghi chú",
    )
    fast_total = 0
    for index, prompt in enumerate(prompts):
        trace = first_trace if index == 0 else runtime.start_turn(
            f"session-{index}", str(brain), "dashboard"
        )
        trace.registry_revision = registry.revision(brain)
        plan = canary.prepare(
            trace, prompt, str(brain), "dashboard", "groq", "llama-3.3", "api"
        )
        assert plan.action == "execute", (prompt, plan.reason)
        fast_total += plan.estimated_input_tokens

    # Baseline dùng fixture TỔNG HỢP đã commit, không đọc brain thật: brains/ nằm
    # trong .gitignore nên bản cũ luôn đỏ ở CI, và Phase 0 cấm benchmark chạm dữ
    # liệu người dùng chưa redaction.
    legacy_system_chars = len((ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
    legacy_system_chars += len((
        ROOT / "tests" / "fixtures" / "legacy_memory_baseline.md"
    ).read_text(encoding="utf-8"))
    conservative_legacy_total = len(prompts) * (legacy_system_chars // 4)
    assert fast_total < conservative_legacy_total * 0.25


def test_tool_candidate_and_stale_registry_fall_back_before_model(tmp_path):
    brain, registry, runtime, trace, canary = _stack(tmp_path)
    registry.refresh_tools(brain, [{
        "name": "explain_entropy",
        "description": "Giải thích entropy",
        "schema": {"type": "object", "properties": {}},
    }], {})
    trace.registry_revision = registry.revision(brain)
    plan = canary.prepare(
        trace, "Giải thích entropy là gì", str(brain), "dashboard",
        "groq", "llama-3.3", "api",
    )
    assert plan.action == "legacy"
    assert plan.reason in ("capability_selected", "capability_ambiguous")


def test_zero_allocation_and_non_dashboard_never_enter_fast_path(tmp_path):
    settings = _settings(allocation=0)
    brain, registry, runtime, trace, canary = _stack(tmp_path, settings)
    plan = canary.prepare(
        trace, "Giải thích entropy là gì", str(brain), "dashboard",
        "groq", "llama-3.3", "api",
    )
    assert plan.action == "legacy" and plan.reason == "outside_allocation"

    brain2, registry2, runtime2, trace2, canary2 = _stack(tmp_path / "second", _settings())
    plan2 = canary2.prepare(
        trace2, "Giải thích entropy là gì", str(brain2), "telegram",
        "groq", "llama-3.3", "api",
    )
    assert plan2.action == "legacy" and plan2.reason == "channel_not_allowed"


def test_known_over_quota_is_rejected_without_messages_or_reservation(tmp_path):
    brain, registry, runtime, trace, canary = _stack(tmp_path, _settings(rolling_tpm=100))
    plan = canary.prepare(
        trace, "Giải thích entropy là gì", str(brain), "dashboard",
        "groq", "llama-3.3", "api",
    )
    assert plan.action == "reject"
    assert not plan.messages
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    admitted = db.execute(
        "SELECT COUNT(*) FROM quota_reservations WHERE status='ADMITTED'"
    ).fetchone()[0]
    assert admitted == 0


def test_atomic_rolling_quota_admission_rejects_concurrent_overcommit(tmp_path):
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    traces = [runtime.start_turn(f"s-{i}", "brain", "dashboard") for i in range(10)]

    def reserve(trace):
        return runtime.admit_quota(trace, "groq", "m", 250, 50, 1000, 60)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(reserve, traces))
    assert sum(x.allowed for x in results) == 3
    assert all(x.reason in ("admitted", "rolling_tpm") for x in results)


def test_admission_accounts_for_recent_legacy_usage_too(tmp_path):
    """Bất biến: lượt legacy vừa đốt token thì canary phải thấy và trừ đi.

    Từ khi có `quota_scheduler`, mức dùng THẬT đi qua `usage_store.record` chứ không còn
    đọc từ bảng đặt chỗ nữa (bảng đó nay chỉ giữ phần ĐANG BAY, để khỏi đếm hai lần). Trong
    production hai lời gọi luôn đi CẶP - có test riêng khoá chuyện đó - nên ở đây gọi đủ
    cặp để đo đúng đường thật.
    """
    import quota_scheduler
    import usage_store

    quota_scheduler.reset()
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    legacy = runtime.start_turn("legacy", "brain", "dashboard")
    runtime.observe_payload(
        legacy, [{"role": "user", "content": "x" * 1200}],
        provider="groq", model="m",
    )
    usage_store.record("groq", "m", 700, 100)
    runtime.record_usage(legacy, 700, 100)
    canary = runtime.start_turn("canary", "brain", "dashboard")
    admission = runtime.admit_quota(canary, "groq", "m", 150, 100, 1000, 60)
    assert not admission.allowed
    assert admission.used_tokens == 800
    assert admission.remaining_tokens == 200
    quota_scheduler.reset()


def test_phase5_schema_migrates_existing_shadow_database_in_place(tmp_path):
    db_path = tmp_path / "runtime.db"
    db = sqlite3.connect(db_path)
    db.executescript("""
        CREATE TABLE runtime_tasks (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL, brain TEXT NOT NULL,
          channel TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL,
          runtime_version TEXT NOT NULL, resolver_policy_version TEXT NOT NULL,
          compiler_policy_version TEXT NOT NULL, registry_revision TEXT NOT NULL,
          model_profile_revision TEXT NOT NULL, budget_json TEXT NOT NULL DEFAULT '{}',
          deadline_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE quota_reservations (
          id TEXT PRIMARY KEY, task_id TEXT NOT NULL, step_id TEXT NOT NULL,
          provider TEXT NOT NULL, model TEXT NOT NULL, input_reserved INTEGER NOT NULL,
          output_reserved INTEGER NOT NULL, status TEXT NOT NULL,
          expires_at REAL NOT NULL, created_at REAL NOT NULL
        );
    """)
    db.close()

    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    runtime._conn()
    migrated = sqlite3.connect(db_path)
    task_columns = {r[1] for r in migrated.execute("PRAGMA table_info(runtime_tasks)")}
    quota_columns = {r[1] for r in migrated.execute("PRAGMA table_info(quota_reservations)")}
    assert {"execution_path", "canary_bucket", "canary_policy_version"} <= task_columns
    assert {"actual_input_tokens", "actual_output_tokens"} <= quota_columns


def test_execution_path_is_pinned_even_if_rollout_config_changes(tmp_path):
    settings = _settings(allocation=0)
    brain, registry, runtime, trace, canary = _stack(tmp_path, settings)
    first = canary.prepare(
        trace, "Giải thích entropy là gì", str(brain), "dashboard",
        "groq", "llama-3.3", "api",
    )
    settings["context_runtime"]["canary"]["allocation_basis_points"] = 10_000
    second = canary.prepare(
        trace, "Giải thích entropy là gì", str(brain), "dashboard",
        "groq", "llama-3.3", "api",
    )
    assert first.execution_path == "legacy"
    assert second.execution_path == "legacy"
    events = [e for e in runtime.list_events(trace.task_id) if e["event_type"] == "canary.decision"]
    assert len(events) == 1


def test_fast_executor_uses_exactly_one_direct_model_stream(monkeypatch):
    import main

    calls = []

    async def fake_events():
        yield {"type": "meta", "model": "llama-test"}
        yield {"type": "text", "content": "Câu trả lời"}

    def fake_stream(provider, key, model, messages, reasoning):
        calls.append((provider, model, messages))
        return fake_events()

    class FakeWS:
        def __init__(self):
            self.events = []

        async def send_text(self, raw):
            self.events.append(json.loads(raw))

    monkeypatch.setattr(main, "_api_stream", fake_stream)
    ws = FakeWS()
    plan = FastPathPlan(
        action="execute", reason="admitted", execution_path="fast",
        messages=({"role": "system", "content": "core"},
                  {"role": "user", "content": "question"}),
        capsule_hash="hash", estimated_input_tokens=10,
    )
    text, model = asyncio.run(main._execute_fast_path(
        plan, "groq", "key", "llama-test", "off", ws, "sid", None, "question"
    ))
    assert text == "Câu trả lời" and model == "llama-test"
    assert len(calls) == 1
    assert [x["type"] for x in ws.events] == ["stream", "response"]
    source = inspect.getsource(main._execute_fast_path)
    assert "_api_stream_mcp" not in source
    assert "compaction." not in source


def test_phase5_defaults_remain_non_impacting():
    config_source = (SERVER / "config.py").read_text(encoding="utf-8")
    assert '"mode": "shadow"' in config_source
    assert '"allocation_basis_points": 0' in config_source


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa
    # từng chạy một assertion nào.
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
