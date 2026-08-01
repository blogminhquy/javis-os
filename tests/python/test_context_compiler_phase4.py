from _paths import ROOT, SERVER  # noqa: E402,F401

import json
import sqlite3

from capability_registry import CapabilityRegistry
from context_compiler import (
    CORE_CONTRACT,
    CompileRequest,
    ContextCompiler,
    DeterministicQualityGate,
    GenericChatRenderer,
    HeuristicTokenizer,
)
from context_runtime import ObserveRuntime


def _tool(name, description, schema=None):
    return {"fn": name, "name": name, "server": "synthetic", "description": description,
            "schema": schema or {"type": "object", "properties": {"q": {"type": "string"}}}}


def _registry(tmp_path, extra=0):
    registry = CapabilityRegistry(tmp_path)
    tools = [
        _tool("calendar_list", "Đọc lịch hôm nay", {
            "type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]
        }),
        _tool("vault_write", "Ghi note vào vault"),
    ]
    route = {
        "calendar_list": {"source_type": "mcp", "source_id": "calendar", "effect": "read",
                          "required_mode": "readonly", "health": "healthy"},
        "vault_write": {"source_type": "builtin", "source_id": "javis", "effect": "write",
                        "required_mode": "safe", "health": "healthy"},
    }
    for i in range(extra):
        name = f"irrelevant_{i:04d}"
        tools.append(_tool(name, f"Unrelated synthetic capability {i}"))
        route[name] = {"source_type": "plugin", "source_id": f"p{i}", "effect": "read",
                       "required_mode": "readonly", "health": "healthy"}
    registry.refresh_tools("brain-a", tools, route)
    registry.refresh_model_profile("groq", "model-a", "api", True, {"observed": True})
    return registry


def _request(**patch):
    data = dict(task_id="task-1", step_id="step-1", objective="Xem lịch hôm nay",
                brain="brain-a", channel="dashboard", provider="groq", model="model-a",
                model_kind="api")
    data.update(patch)
    return CompileRequest(**data)


def _selected(registry, name="calendar_list"):
    item = registry.search(name, "brain-a")[0]
    return {"selected": [{"capability_id": item["capability_id"], "name": item["name"]}]}


def test_core_contract_is_small_and_provider_independent(tmp_path):
    fixture = json.loads(
        (ROOT / "tests/fixtures/context_compiler_contract.json").read_text(encoding="utf-8")
    )
    assert len(CORE_CONTRACT) < 1800
    for term in fixture["required_terms"]:
        assert term in CORE_CONTRACT
    for term in fixture["forbidden_terms"]:
        assert term not in CORE_CONTRACT

    registry = _registry(tmp_path)
    compiler = ContextCompiler(registry)
    for provider in fixture["providers"]:
        result = compiler.compile_shadow(
            _request(provider=provider, model=f"{provider}-model"), {"selected": []}
        )
        assert result.status == "compiled"
        system = result.capsule.rendered_request["messages"][0]["content"]
        assert all(term in system for term in fixture["required_terms"])


def test_fast_capsule_has_source_map_and_is_within_final_budget(tmp_path):
    compiler = ContextCompiler(_registry(tmp_path))
    result = compiler.compile_shadow(_request(), {"selected": []})
    assert result.status == "compiled"
    assert result.capsule.path == "fast"
    assert result.capsule.capabilities == ()
    assert result.trace_report["estimated_input_tokens"] <= result.trace_report["max_input_tokens"]
    assert result.trace_report["preflight_decision"] == "would_allow"
    assert result.trace_report["observe_only"] is True
    assert set(result.capsule.source_map) == {"core", "channel", "output", "objective"}
    assert result.trace_report["source_map_hash"]


def test_renderer_adapter_is_counted_after_final_render(tmp_path):
    class ProviderRenderer(GenericChatRenderer):
        revision = "provider-demo-v1"

        def render(self, system, user, tools):
            payload = super().render(system, user, tools)
            payload["response_format"] = {"type": "text"}
            return payload

    compiler = ContextCompiler(_registry(tmp_path), renderer=ProviderRenderer())
    result = compiler.compile_shadow(_request(), {"selected": []})
    assert result.status == "compiled"
    assert result.trace_report["renderer_revision"] == "provider-demo-v1"
    expected = HeuristicTokenizer("groq", "model-a").count_rendered(
        result.capsule.rendered_request
    )
    assert expected.input_tokens == result.trace_report["estimated_input_tokens"]


def test_tool_capsule_uses_exact_selected_schema_only(tmp_path):
    registry = _registry(tmp_path)
    result = ContextCompiler(registry).compile_shadow(_request(), _selected(registry))
    assert result.status == "compiled"
    assert result.capsule.path == "tool"
    assert len(result.capsule.capabilities) == 1
    fn = result.capsule.capabilities[0]["function"]
    assert fn["name"] == "calendar_list"
    assert fn["parameters"]["required"] == ["date"]
    assert "vault_write" not in json.dumps(result.capsule.rendered_request)
    assert result.trace_report["tool_tokens"] > 0
    assert result.trace_report["selection_reason"] == "resolver_rank_then_budget_fit"
    assert result.trace_report["estimated_input_tokens"] <= result.trace_report["max_input_tokens"]


def test_required_items_too_large_returns_explicit_failure_not_silent_trim(tmp_path):
    registry = _registry(tmp_path)
    registry.refresh_model_profile("tiny", "tiny-model", "api", True, {
        "max_input_tokens": 120, "reserved_output_tokens": 50
    })
    compiler = ContextCompiler(registry)
    result = compiler.compile_shadow(_request(
        provider="tiny", model="tiny-model", objective="x" * 5000
    ), {"selected": []})
    assert result.status == "required_items_too_large"
    assert result.capsule is None
    assert result.trace_report["preflight_decision"] == "would_reject"


def test_irrelevant_capabilities_do_not_change_capsule_or_tokens(tmp_path):
    base_registry = _registry(tmp_path / "base")
    large_registry = _registry(tmp_path / "large", extra=400)
    base = ContextCompiler(base_registry).compile_shadow(_request(), _selected(base_registry))
    large = ContextCompiler(large_registry).compile_shadow(_request(), _selected(large_registry))
    assert base.capsule.capsule_hash == large.capsule.capsule_hash
    assert base.trace_report["estimated_input_tokens"] == large.trace_report["estimated_input_tokens"]
    assert base.trace_report["selected_count"] == large.trace_report["selected_count"] == 1


def test_budget_explains_excluded_schema(tmp_path):
    registry = _registry(tmp_path)
    huge = _tool("huge_tool", "Huge schema", {
        "type": "object", "properties": {
            f"field_{i}": {"type": "string", "description": "z" * 200} for i in range(150)
        }
    })
    tools = [huge]
    route = {"huge_tool": {"source_type": "mcp", "source_id": "huge", "effect": "read",
                           "required_mode": "readonly", "health": "healthy"}}
    registry.refresh_tools("brain-b", tools, route)
    registry.refresh_model_profile("tiny", "budgeted", "api", True, {
        "max_input_tokens": 700, "reserved_output_tokens": 100
    })
    cap = registry.search("huge", "brain-b")[0]
    request = _request(task_id="t2", step_id="s2", brain="brain-b", provider="tiny", model="budgeted")
    result = ContextCompiler(registry).compile_shadow(
        request, {"selected": [{"capability_id": cap["capability_id"]}]}
    )
    assert result.status == "compiled"
    assert result.trace_report["selected_count"] == 0
    assert result.trace_report["excluded"][cap["capability_id"]] == "budget"
    assert result.trace_report["estimated_input_tokens"] <= 700


def test_quality_gate_baselines_legacy_output_without_changing_it():
    gate = DeterministicQualityGate()
    assert gate.evaluate("q", "Câu trả lời bình thường", "dashboard").status == "pass"
    assert gate.evaluate("q", "", "dashboard").status == "fail"
    leaked = gate.evaluate("q", "[JAVIS_ASK] raw control", "dashboard")
    assert leaked.status == "revise" and "control_block_leak" in leaked.reasons
    denied = gate.evaluate(
        "q", "Em không có tool để đọc lịch", "dashboard",
        compiler_report={"selected_count": 1},
    )
    assert denied.status == "gather_more"
    assert gate.evaluate("q", "x" * 9000, "telegram").status == "revise"


def test_compiler_and_quality_trace_are_metadata_only(tmp_path):
    runtime = ObserveRuntime(
        tmp_path / "runtime",
        settings_reader=lambda: {"context_runtime": {"mode": "shadow", "retention_days": 14}},
    )
    trace = runtime.start_turn("sid", "brain-a", "dashboard")
    private = "PRIVATE OBJECTIVE MUST NOT PERSIST"
    report = {
        "status": "compiled", "path": "fast", "capsule_hash": "abc",
        "estimated_input_tokens": 100, "max_input_tokens": 8000,
        "selected_ids": [], "excluded": {}, "preflight_decision": "would_allow",
    }
    runtime.record_compiler_shadow(trace, report)
    runtime.record_quality_shadow(trace, {
        "status": "pass", "reason_codes": [], "confidence": 0.9,
        "response_chars": len(private),
    })
    runtime.finish(trace)
    runtime.close()
    raw = (tmp_path / "runtime" / "runtime.db").read_bytes()
    assert private.encode() not in raw
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    kinds = [x[0] for x in db.execute(
        "SELECT event_type FROM runtime_events WHERE task_id=? ORDER BY seq", (trace.task_id,)
    )]
    assert "compiler.shadow" in kinds
    assert "quality.shadow" in kinds


def test_tokenizer_counts_final_rendered_payload_and_runtime_calibrates(tmp_path):
    tok = HeuristicTokenizer("groq", "model-a", chars_per_token=3.0)
    estimate = tok.count_request("system", "user", [{"name": "tool"}])
    assert estimate.input_tokens >= estimate.system_tokens + estimate.user_tokens

    runtime = ObserveRuntime(
        tmp_path,
        settings_reader=lambda: {"context_runtime": {"mode": "shadow", "retention_days": 14}},
    )
    trace = runtime.start_turn("sid", "brain", "dashboard")
    runtime.set_route(trace, "groq", "model-a")
    runtime.observe_payload(trace, [{"role": "user", "content": "x" * 300}],
                            provider="groq", model="model-a")
    runtime.record_usage(trace, 120, 10)
    stats = runtime.token_estimate_stats("groq", "model-a")
    assert stats["samples"] == 1
    assert stats["median_abs_pct_error"] >= 0


def test_phase4_is_shadow_only_by_construction():
    source = (SERVER / "context_compiler.py").read_text(encoding="utf-8")
    main_source = (SERVER / "main.py").read_text(encoding="utf-8")
    assert "def generate(" not in source
    assert "observe_only" in source
    assert "_CONTEXT_COMPILER.compile_shadow" in main_source
    assert "await asyncio.to_thread(" in main_source
