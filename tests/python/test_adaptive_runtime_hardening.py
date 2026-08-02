"""Hồi quy cho các lỗi tìm ra khi review lại Phase 0-8 trước khi sang Phase 9.

Mỗi test dưới đây gắn với một lỗi CỤ THỂ đã tái hiện được, không phải test trang trí.
"""
from _paths import SERVER, ROOT  # noqa: E402,F401

import asyncio
import json
import sqlite3
import time

from cryptography.fernet import Fernet

import capability_resolver
import fast_path_runtime
import readonly_path_runtime
from adaptive_context_runtime import FeaturePolicy
from capability_executor import CapabilityExecutor
from capability_registry import CapabilityRegistry
from context_compiler import (
    CompileRequest, ContextCompiler, ContextItem, DeterministicQualityGate,
)
from context_runtime import ObserveRuntime
from evidence_store import EvidenceStore, redact
from memory_index import MemoryIndex


# ---------------------------------------------------------------- Phase 0-1

def test_malformed_settings_never_break_a_turn(tmp_path):
    """settings.json sai kiểu từng làm sập websocket ngay ở start_turn."""
    for broken in ("off", {"context_runtime": "off"},
                   {"context_runtime": {"retention_days": "hai tuần"}},
                   {"context_runtime": {"estimate_chars_per_token": "ba"}}):
        settings = broken if isinstance(broken, dict) else {"context_runtime": broken}
        runtime = ObserveRuntime(tmp_path / str(abs(hash(str(broken)))),
                                 settings_reader=lambda s=settings: s)
        assert runtime.enabled() in (True, False)
        trace = runtime.start_turn("session-broken", str(tmp_path), "dashboard")
        runtime.record_usage(trace, 10, 5)
        runtime.finish(trace, "COMPLETED")
        runtime.close()


def test_settings_reader_exception_falls_back_to_off(tmp_path):
    def boom():
        raise RuntimeError("settings unreadable")

    runtime = ObserveRuntime(tmp_path, settings_reader=boom)
    assert runtime.enabled() is False
    assert runtime.start_turn("s", str(tmp_path), "dashboard") is None


def test_expired_reservation_still_records_real_usage(tmp_path):
    """Reservation hết TTL giữa stream từng nuốt mất usage thật khỏi rolling window."""
    settings = {"context_runtime": {"mode": "canary"}}
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: settings)
    trace = runtime.start_turn("session-quota", str(tmp_path), "dashboard")
    admission = runtime.admit_quota(trace, "groq", "llama-3.3", 500, 100, 100_000, 1)
    assert admission.allowed
    time.sleep(1.1)
    # Bất kỳ admission nào khác cũng chạy reaper và lật reservation sang EXPIRED.
    other = runtime.start_turn("session-quota-2", str(tmp_path), "dashboard")
    runtime.admit_quota(other, "groq", "llama-3.3", 10, 10, 100_000, 60)
    runtime.consume_quota(trace, admission.reservation_id, 480, 90)
    runtime.close()
    db = sqlite3.connect(tmp_path / "runtime.db")
    row = db.execute(
        "SELECT status,actual_input_tokens,actual_output_tokens FROM quota_reservations "
        "WHERE id=?", (admission.reservation_id,)
    ).fetchone()
    assert row == ("CONSUMED", 480, 90)


def test_evidence_metadata_rejects_plaintext_and_escaping_paths(tmp_path):
    settings = {"context_runtime": {"mode": "canary"}}
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: settings)
    trace = runtime.start_turn("session-ev", str(tmp_path), "dashboard")
    assert runtime.persist_evidence_metadata(
        trace, "ev1", "capability_read", "ref", "application/json",
        "task/ev1.enc", "plaintext excerpt", "0" * 64, "tool_result") is False
    assert runtime.persist_evidence_metadata(
        trace, "ev2", "capability_read", "ref", "application/json",
        "../../etc/passwd", "enc:xxx", "0" * 64, "tool_result") is False
    assert runtime.persist_evidence_metadata(
        trace, "ev3", "capability_read", "ref", "application/json",
        "task/ev3.enc", "enc:xxx", "0" * 64, "tool_result") is True
    runtime.close()


# ---------------------------------------------------------------- Phase 2-3

def _registry_with_plugin(tmp_path):
    registry = CapabilityRegistry(tmp_path / "registry")
    brain = tmp_path / "brain"
    tools = [
        {"fn": "mcp_read", "name": "mcp_read", "description": "đọc lịch",
         "schema": {"type": "object", "properties": {}}},
        {"fn": "plugin_calc", "name": "plugin_calc", "description": "tính lãi kép",
         "schema": {"type": "object", "properties": {}}},
    ]
    routes = {
        "mcp_read": {"source_type": "mcp", "source_id": "cal", "effect": "read",
                     "required_mode": "readonly", "health": "healthy",
                     "call": lambda args: None},
        "plugin_calc": {"source_type": "plugin", "source_id": "calc", "effect": "read",
                        "required_mode": "readonly", "health": "healthy",
                        "call": lambda args: None},
    }
    registry.refresh_tools(brain, tools, routes)
    return registry, brain, tools, routes


def test_removing_a_plugin_source_deactivates_its_capabilities(tmp_path):
    registry, brain, tools, routes = _registry_with_plugin(tmp_path)
    assert any(x["name"] == "plugin_calc" for x in registry.search("tính lãi kép", brain, 20))
    registry.refresh_tools(brain, [tools[0]], {"mcp_read": routes["mcp_read"]})
    assert not [x for x in registry.search("tính lãi kép", brain, 20)
                if x["name"] == "plugin_calc"]


def test_duplicate_tool_names_do_not_wipe_the_whole_registry(tmp_path):
    registry = CapabilityRegistry(tmp_path / "registry")
    brain = tmp_path / "brain"
    schema = {"type": "object", "properties": {}}
    dupe = {"fn": "same", "name": "same", "description": "trùng tên", "schema": schema}
    route = {"same": {"source_type": "mcp", "source_id": "s1", "effect": "read",
                      "required_mode": "readonly", "health": "healthy",
                      "call": lambda args: None}}
    result = registry.refresh_tools(brain, [dupe, dict(dupe)], route)
    assert result["capability_count"] >= 1
    assert registry.search("trùng tên", brain, 10)


# ---------------------------------------------------------------- Phase 4

def _item(item_id, content, **kwargs):
    defaults = dict(kind="memory_fact", source_ref="file:x", token_cost=10,
                    relevance=1.0, confidence=1.0, authority=1.0, freshness=1.0,
                    required=False, trust="memory_source")
    defaults.update(kwargs)
    return ContextItem(id=item_id, content=content, **defaults)


def _request(tmp_path, items=(), **kwargs):
    base = dict(task_id="t1", step_id="s1", objective="doanh thu tháng này ra sao",
                brain=str(tmp_path), channel="dashboard", provider="groq",
                model="llama-3.3", model_kind="api", context_items=tuple(items))
    base.update(kwargs)
    return CompileRequest(**base)


def test_task_budget_reserves_output_before_declaring_compiled(tmp_path):
    """compiled + preflight would_reject vì task_budget là mâu thuẫn nội bộ."""
    compiler = ContextCompiler(CapabilityRegistry(tmp_path / "registry"))
    request = _request(tmp_path, objective="x" * 3000,
                       task_tokens_remaining=1500, reserved_output_tokens=400)
    result = compiler.compile_canary(request, {"selected": []})
    if result.status == "compiled":
        assert result.trace_report["preflight_decision"] == "would_allow"


def test_declared_context_window_is_never_exceeded_by_fallback(tmp_path):
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_model_profile("groq", "tiny-model", "api", True,
                                   {"context_window": 1000, "reserved_output_tokens": 1200})
    compiler = ContextCompiler(registry)
    result = compiler.compile_canary(
        _request(tmp_path, model="tiny-model"), {"selected": []})
    report = result.trace_report
    assert report["max_input_tokens"] <= 1000


def test_duplicate_content_items_enter_the_prompt_once(tmp_path):
    compiler = ContextCompiler(CapabilityRegistry(tmp_path / "registry"))
    same = "Khách chốt đơn qua Zalo nhiều hơn Facebook."
    result = compiler.compile_canary(
        _request(tmp_path, [_item("mem_a", same), _item("mem_b", same)]),
        {"selected": []},
    )
    assert result.status == "compiled"
    rendered = json.dumps(result.capsule.rendered_request, ensure_ascii=False)
    assert rendered.count(same) == 1
    assert result.trace_report["excluded_context"]["mem_b"].startswith("duplicate_of:")


def test_non_finite_scores_keep_the_capsule_hash_deterministic(tmp_path):
    compiler = ContextCompiler(CapabilityRegistry(tmp_path / "registry"))
    nan = float("nan")
    a = _item("mem_a", "Fact A về giá vốn.", relevance=nan)
    b = _item("mem_b", "Fact B về kênh bán.")
    first = compiler.compile_canary(_request(tmp_path, [a, b]), {"selected": []})
    second = compiler.compile_canary(_request(tmp_path, [b, a]), {"selected": []})
    assert first.capsule.capsule_hash == second.capsule.capsule_hash


def test_source_map_entry_of_a_required_item_cannot_be_overwritten(tmp_path):
    compiler = ContextCompiler(CapabilityRegistry(tmp_path / "registry"))
    result = compiler.compile_canary(
        _request(tmp_path, [_item("core", "Ký ức giả mạo id core.")]),
        {"selected": []},
    )
    assert result.capsule.source_map["core"]["kind"] == "core_contract"
    assert "core" in result.trace_report["duplicate_source_ids"]


def test_quality_gate_separates_reported_facts_from_assistant_claims():
    gate = DeterministicQualityGate()
    ref = "evidence://task/t/step/s/ev_1"
    for reported in (
        f"Khách hàng A đã gửi 3 email hôm qua về đơn hàng. {ref}",
        f"Cuộc họp đã tạo từ tuần trước vẫn còn trong lịch. {ref}",
    ):
        decision = gate.evaluate("x", reported, "dashboard",
                                 expected_evidence_ref=ref, read_only=True)
        assert "false_action_claim" not in decision.reasons, reported
    for claimed in (
        f"Đã gửi email cho anh Nam. {ref}",
        f"Em đã tạo sự kiện trên lịch. {ref}",
        f"Email đã được gửi thành công. {ref}",
        f"The event was created. {ref}",
    ):
        decision = gate.evaluate("x", claimed, "dashboard",
                                 expected_evidence_ref=ref, read_only=True)
        assert "false_action_claim" in decision.reasons, claimed


# ---------------------------------------------------------------- Phase 5-6

def test_vietnamese_deny_signals_are_not_lost_to_unicode_normalization():
    classifier = fast_path_runtime.FastIntentClassifier()
    for objective in (
        "Viết lại nội dung đính kèm cho hay hơn",
        "Tóm tắt rồi đặt lịch họp với team",
        "Viết bài rồi đăng lên Facebook",
        "Tóm tắt bài viết này: https://vnexpress.net/abc.html",
        "Tóm tắt cuộc trò chuyện này",
        "Dịch tin nhắn trước sang tiếng Anh",
        "Tính tổng doanh thu tháng này",
        "Summarize my last message",
        "Translate the document I uploaded",
    ):
        decision = classifier.classify(objective)
        assert not decision.eligible, (objective, decision.intent_class)


def test_write_intent_with_diacritics_stays_on_legacy():
    assert readonly_path_runtime._WRITE_INTENT.search(
        readonly_path_runtime._norm("Đặt lịch họp ngày mai"))
    assert readonly_path_runtime._WRITE_INTENT.search(
        readonly_path_runtime._norm("Đăng bài lên trang"))


def test_quota_rule_matching_is_case_insensitive():
    policy = fast_path_runtime.CanaryPolicy.from_settings({"context_runtime": {
        "mode": "canary",
        "canary": {"quota_profiles": [
            {"id": "specific", "provider": "groq", "model_pattern": "llama-*",
             "rolling_tpm": 1000, "max_input_tokens": 5000,
             "reserved_output_tokens": 500, "window_seconds": 60},
            {"id": "catch-all", "provider": "groq", "model_pattern": "*",
             "rolling_tpm": 10, "max_input_tokens": 100,
             "reserved_output_tokens": 10, "window_seconds": 60},
        ]},
    }})
    assert policy.quota_rule("groq", "LLAMA-3.3").rule_id == "specific"


def test_undeclared_arguments_are_denied_by_default(tmp_path):
    settings = {"context_runtime": {"mode": "canary"}}
    registry = CapabilityRegistry(tmp_path / "registry")
    brain = tmp_path / "brain"
    schema = {"type": "object", "properties": {"date": {"type": "string"}},
              "required": ["date"]}   # KHÔNG khai additionalProperties
    tool = {"fn": "cal_list", "name": "cal_list", "description": "đọc lịch", "schema": schema}
    called = []

    async def call(args):
        called.append(dict(args))
        return {"ok": True}

    routes = {"cal_list": {"source_type": "mcp", "source_id": "cal", "effect": "read",
                           "required_mode": "readonly", "health": "healthy", "call": call}}
    registry.refresh_tools(brain, [tool], routes)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-args", str(brain), "dashboard")
    fernet = Fernet(Fernet.generate_key())
    store = EvidenceStore(
        runtime, tmp_path / "runtime",
        encryptor=lambda v: "enc:" + fernet.encrypt(v.encode()).decode(),
        decryptor=lambda v: fernet.decrypt(v[4:].encode()).decode(),
        ready_check=lambda: True,
    )
    executor = CapabilityExecutor(registry, runtime, store)
    capability = registry.get_capabilities(
        [x["capability_id"] for x in registry.search("đọc lịch", brain, 5)], brain)[0]
    lease = executor.issue_lease(trace, "actor", str(brain), capability, {"id": "p1"})
    result = asyncio.run(executor.invoke(
        trace, "actor", lease, {"date": "2026-08-02", "op": "delete_all"}, call))
    assert result.status == "FAILED_VALIDATION" and not called


def test_redaction_covers_common_credential_shapes():
    payload = {
        "x-api-key": "abc123456789",
        "note": "token JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.dBjftJeZ4CVPmB92K27u",
        "aws": "AKIAIOSFODNN7EXAMPLE",
        "google": "AIzaSyD-abcdefghijklmnopqrstuvwxyz12345",
        "url": "https://api.example.com/v1/data?token=supersecretvalue123&page=2",
    }
    safe = redact(payload)
    blob = json.dumps(safe, ensure_ascii=False)
    for secret in ("abc123456789", "eyJhbGciOiJIUzI1NiJ9", "AKIAIOSFODNN7EXAMPLE",
                   "AIzaSyD-abcdefghijklmnopqrstuvwxyz12345", "supersecretvalue123"):
        assert secret not in blob, secret


# ---------------------------------------------------------------- Phase 8

def test_memory_line_refs_point_at_the_real_source_lines(tmp_path):
    """Ref lệch dòng từng khiến _read_detail thay excerpt đúng bằng fact khác."""
    brain = tmp_path / "brain"
    memory = brain / "Memory"
    memory.mkdir(parents=True)
    text = (
        "---\ntype: business\n---\n\n"
        "# Giá sản phẩm\n\n"
        "Giá bán lẻ: 120k mỗi chai nước mắm cao đạm.\n\n"
        "Giá sỉ: 100k mỗi chai khi lấy trên 50 thùng.\n\n"
        "# Kênh bán\n\n"
        "Kênh chính là Facebook và Zalo cho khách quen.\n"
    )
    (memory / "facts.md").write_text(text, encoding="utf-8")
    index = MemoryIndex(tmp_path / "state")
    index.rebuild(brain)
    lines = text.splitlines()
    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    rows = list(db.execute(
        "SELECT excerpt,line_start,line_end FROM memory_records ORDER BY line_start"))
    assert rows
    for excerpt, line_start, line_end in rows:
        actual = " ".join("\n".join(lines[line_start - 1:line_end]).split())
        assert actual == " ".join(excerpt.split()), (line_start, line_end, excerpt)


def test_memory_index_rebuilds_when_schema_version_changes(tmp_path):
    brain = tmp_path / "brain"
    memory = brain / "Memory"
    memory.mkdir(parents=True)
    (memory / "facts.md").write_text("# Ghi chú\n\nKhách quen mua lại mỗi tháng.\n",
                                     encoding="utf-8")
    index = MemoryIndex(tmp_path / "state")
    assert index.rebuild(brain)["rebuilt"] is True
    assert index.rebuild(brain)["rebuilt"] is False
    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    db.execute("UPDATE index_meta SET schema_version='memory-index-v0'")
    db.commit()
    db.close()
    index = MemoryIndex(tmp_path / "state")
    assert index.rebuild(brain)["rebuilt"] is True


def test_phase8_policies_survive_malformed_operator_settings():
    policy = FeaturePolicy.from_settings({"context_runtime": {"memory_canary": {
        "allocation_basis_points": "abc", "min_confidence": "high",
        "max_items": "nhiều", "recent_messages": None,
    }}}, "memory_canary")
    assert policy.allocation_basis_points == 0
    assert 0.0 <= policy.min_confidence <= 1.0


def test_resolver_never_returns_capabilities_outside_the_actor_effects(tmp_path):
    registry = CapabilityRegistry(tmp_path / "registry")
    brain = tmp_path / "brain"
    tool = {"fn": "send_mail", "name": "send_mail", "description": "gửi email cho khách",
            "schema": {"type": "object", "properties": {}}}
    routes = {"send_mail": {"source_type": "mcp", "source_id": "mail", "effect": "write",
                            "required_mode": "safe", "health": "healthy",
                            "call": lambda args: None}}
    registry.refresh_tools(brain, [tool], routes)
    resolver = capability_resolver.DeterministicResolver(registry)
    result = resolver.resolve("gửi email cho khách", brain, capability_resolver.ActorPolicy(
        mode="readonly", channel="dashboard",
        allowed_effects=frozenset({"none", "read"})))
    assert not result.get("selected")


# ------------------------------------------- bất biến chung của cả 9 phase

def test_repository_defaults_activate_no_canary_path(tmp_path):
    """Một test canh bất biến quan trọng nhất: cài mặc định KHÔNG đổi hành vi ai cả.

    Kiểm bằng cách chạy thật admission của cả năm đường canary với chính hằng
    mặc định trong config.py, không phải bằng cách grep chuỗi trong source.
    """
    import copy
    import asyncio
    import config as cfgmod
    import agent_runtime
    import fast_path_runtime
    import model_router
    import readonly_path_runtime
    import readonly_orchestrator
    import workflow_graph
    import workflow_runtime
    import write_path_runtime
    from adaptive_context_runtime import AdaptiveContextCanary
    from capability_executor import CapabilityExecutor
    from context_compiler import get_quality_gate
    from evidence_store import EvidenceStore

    settings = copy.deepcopy(cfgmod._DEFAULT)
    runtime_cfg = settings["context_runtime"]
    assert runtime_cfg["mode"] == "shadow"
    for key, value in runtime_cfg.items():
        if isinstance(value, dict) and "allocation_basis_points" in value:
            assert value["allocation_basis_points"] == 0, key
        if isinstance(value, dict) and "quota_profiles" in value:
            assert value["quota_profiles"] == [], key
        if isinstance(value, dict) and "capability_profiles" in value:
            assert value["capability_profiles"] == [], key

    brain = tmp_path / "brain"
    registry = CapabilityRegistry(tmp_path / "reg")
    tools = [{"fn": "calendar_create", "name": "calendar_create",
              "description": "tạo sự kiện lịch calendar create",
              "schema": {"type": "object", "properties": {}}}]
    routes = {"calendar_create": {
        "source_type": "mcp", "source_id": "cal", "effect": "write",
        "required_mode": "safe", "health": "healthy", "call": lambda a: None}}
    registry.refresh_tools(brain, tools, routes)
    runtime = ObserveRuntime(tmp_path / "rt", settings_reader=lambda: settings)
    trace = runtime.start_turn("sid", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    compiler = ContextCompiler(registry)
    executor = CapabilityExecutor(
        registry, runtime, EvidenceStore(runtime, tmp_path / "rt"))
    resolver = capability_resolver.DeterministicResolver(registry)

    async def discover(mode, root):
        return tools, routes

    objective = "tạo sự kiện lịch calendar create"
    plans = {
        "fast": fast_path_runtime.FastPathCanary(
            registry, resolver, compiler, runtime, lambda: settings
        ).prepare(trace, objective, str(brain), "dashboard", "groq", "llama-3.3", "api"),
        "readonly": asyncio.run(readonly_path_runtime.ReadonlyPathCanary(
            registry, resolver, compiler, runtime, executor, lambda: settings, discover
        ).prepare(trace, objective, str(brain), "dashboard", "groq", "llama-3.3",
                  "api", "actor")),
        "orchestrator": asyncio.run(readonly_orchestrator.ReadonlyOrchestrator(
            registry, resolver, compiler, runtime, executor, lambda: settings,
            discover, get_quality_gate()
        ).prepare(trace, objective, str(brain), "dashboard", "groq", "llama-3.3",
                  "api", "actor")),
        "write": asyncio.run(write_path_runtime.WritePathCanary(
            registry, resolver, compiler, runtime, executor, lambda: settings, discover
        ).prepare(trace, objective, str(brain), "dashboard", "groq", "llama-3.3",
                  "api", "actor")),
        "context_sources": AdaptiveContextCanary(
            tmp_path / "st", registry, compiler, runtime, lambda: settings
        ).prepare(trace, objective, brain, "sid", [], "dashboard", "groq",
                  "llama-3.3", "api", lambda memory, skills: "base"),
        # Phase 10-12. Test này là hàng rào cuối cùng chống việc vô tình bật một
        # đường canary ở mặc định, nên nó phải phủ HẾT, không được rơi rớt phase nào.
        "workflow": workflow_runtime.WorkflowCanary(
            runtime, lambda: settings
        ).prepare(trace, workflow_graph.compile_workflow(
            {"name": "demo", "steps": [{"agent": "a", "task": "t"}]}, "demo"), "sid"),
    }
    agent_admitted, _b, agent_reason = agent_runtime.AgentPolicy.from_settings(
        settings).admits("demo", "sid")
    assert not agent_admitted, f"agent canary bật ở mặc định: {agent_reason}"
    routed = model_router.ModelRouter(lambda: settings).route(
        model_router.RoutingRequest(), "sid", "groq", "model-cua-user")
    assert routed.action == "keep" and routed.model == "model-cua-user", (
        "model router đổi model ở mặc định")
    for name, plan in plans.items():
        assert plan.action in ("not_applicable", "legacy"), (name, plan.action, plan.reason)


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
